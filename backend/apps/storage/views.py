from __future__ import annotations

import io
import zipfile

from django.conf import settings
from django.db.models import Q
from django.http import Http404, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView

from apps.audit.services import journaliser
from apps.accounts.models import Service
from apps.common.exceptions import (
    ChecksumInvalide,
    OperationInvalide,
    PermissionRefusee,
)
from apps.common.object_storage import cle_objet, sha256_flux, stockage
from apps.sharing.models import Niveau
from apps.storage.permissions_utils import peut_ecrire
from apps.sharing.services import (
    dossiers_visibles,
    exiger,
    fichiers_visibles,
    niveau_sur_fichier,
)

from . import edition, services
from .models import (
    Comment,
    File,
    FileMetadata,
    FileVersion,
    Folder,
    Tag,
    UploadSession,
    est_editable,
)
from .serializers import (
    CommentSerializer,
    FileDetailSerializer,
    FileMetadataSerializer,
    FileSerializer,
    FileVersionSerializer,
    FolderSerializer,
    TagSerializer,
    UploadInitSerializer,
)


class FolderViewSet(viewsets.ModelViewSet):
    serializer_class = FolderSerializer

    def get_queryset(self):
        requete = dossiers_visibles(self.request.user).select_related("owner", "service")
        parent = self.request.query_params.get("parent")
        if parent:
            requete = requete.filter(parent_id=parent)
        elif self.action == "list":
            requete = requete.filter(Q(parent__isnull=True) | Q(is_service_root=True))
        return requete

    def get_object(self):
        dossier = get_object_or_404(Folder, pk=self.kwargs["pk"])
        exiger(self.request.user, dossier, Niveau.READ)
        return dossier

    def perform_create(self, serializer):
        """Cree un sous-dossier, ou un espace de service si aucun parent n'est
        fourni. Un espace racine est structurant pour toute la Direction : sa
        creation reste reservee a l'administrateur."""
        parent_id = self.request.data.get("parent")
        service_id = self.request.data.get("service")

        if not parent_id:
            if not self.request.user.est_admin:
                raise PermissionRefusee(
                    "Seul un administrateur peut creer un espace racine. "
                    "Ouvrez un espace existant pour y creer un dossier."
                )
            service = (
                get_object_or_404(Service, pk=service_id)
                if service_id
                else self.request.user.service
            )
            dossier = services.creer_dossier(
                nom=serializer.validated_data["name"],
                parent=None,
                auteur=self.request.user,
                service=service,
                est_racine_service=bool(service),
            )
            if service and service.root_folder_id is None:
                service.root_folder = dossier
                service.save(update_fields=["root_folder", "updated_at"])
            serializer.instance = dossier
            return

        parent = get_object_or_404(Folder, pk=parent_id)
        exiger(self.request.user, parent, Niveau.WRITE)
        dossier = services.creer_dossier(
            nom=serializer.validated_data["name"],
            parent=parent,
            auteur=self.request.user,
            service=(
                get_object_or_404(Service, pk=service_id) if service_id else None
            ),
        )
        serializer.instance = dossier

    def perform_update(self, serializer):
        dossier = self.get_object()
        exiger(self.request.user, dossier, Niveau.WRITE)
        nouveau_nom = serializer.validated_data.get("name")
        if nouveau_nom and nouveau_nom != dossier.name:
            services.renommer_dossier(dossier, nouveau_nom, self.request.user)
        serializer.save(name=dossier.name)

    def perform_destroy(self, instance):
        exiger(self.request.user, instance, Niveau.WRITE)
        instance.mettre_a_la_corbeille(self.request.user)
        journaliser("FOLDER_DELETE", acteur=self.request.user, cible=instance)

    @action(detail=True, methods=["get"])
    def children(self, request, pk=None):
        dossier = self.get_object()
        sous_dossiers = dossiers_visibles(request.user).filter(parent=dossier)
        fichiers = fichiers_visibles(request.user).filter(folder=dossier)
        kind = request.query_params.get("kind")
        if kind:
            fichiers = fichiers.filter(kind=kind)
        return Response(
            {
                "dossier": FolderSerializer(dossier, context={"request": request}).data,
                "fil_ariane": dossier.fil_ariane(),
                "dossiers": FolderSerializer(
                    sous_dossiers, many=True, context={"request": request}
                ).data,
                "fichiers": FileSerializer(
                    fichiers.select_related("owner", "current_version").prefetch_related("tags"),
                    many=True,
                    context={"request": request},
                ).data,
            }
        )

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        dossier = self.get_object()
        exiger(request.user, dossier, Niveau.WRITE)
        cible = get_object_or_404(Folder, pk=request.data.get("target_parent"))
        exiger(request.user, cible, Niveau.WRITE)
        services.deplacer_dossier(dossier, cible, request.user)
        return Response(FolderSerializer(dossier, context={"request": request}).data)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """Archive ZIP du sous-arbre, generee en flux : un dossier de 2 Go ne
        doit jamais tenir en memoire."""
        dossier = self.get_object()
        exiger(request.user, dossier, Niveau.READ)
        fichiers = fichiers_visibles(request.user).filter(
            folder__path__startswith=dossier.path
        ).select_related("folder", "current_version")

        tampon = io.BytesIO()
        with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
            for fichier in fichiers:
                if not fichier.current_version_id:
                    continue
                chemin_relatif = (
                    fichier.folder.path[len(dossier.path):] + fichier.name
                ).lstrip("/")
                with stockage().lire(fichier.current_version.storage_key) as contenu:
                    archive.writestr(chemin_relatif, contenu.read())
        tampon.seek(0)
        journaliser("FILE_DOWNLOAD", acteur=request.user, cible=dossier, archive=True)
        reponse = StreamingHttpResponse(tampon, content_type="application/zip")
        reponse["Content-Disposition"] = f'attachment; filename="{dossier.name}.zip"'
        return reponse

    @action(detail=False, methods=["get"])
    def tree(self, request):
        """Arbre allege, destine au cache hors ligne."""
        dossiers = dossiers_visibles(request.user).values(
            "id", "name", "parent", "path", "depth", "service", "updated_at"
        )
        return Response(list(dossiers))


class FileViewSet(viewsets.ModelViewSet):
    serializer_class = FileSerializer

    def get_queryset(self):
        return fichiers_visibles(self.request.user).select_related(
            "owner", "folder", "current_version"
        )

    def get_serializer_class(self):
        return FileDetailSerializer if self.action == "retrieve" else FileSerializer

    def get_object(self):
        fichier = get_object_or_404(File, pk=self.kwargs["pk"])
        exiger(self.request.user, fichier, Niveau.READ)
        return fichier

    def perform_update(self, serializer):
        fichier = self.get_object()
        exiger(self.request.user, fichier, Niveau.WRITE)
        nouveau_nom = serializer.validated_data.get("name")
        if nouveau_nom and nouveau_nom != fichier.name:
            services.renommer_fichier(fichier, nouveau_nom, self.request.user)
        serializer.save(name=fichier.name)

    def perform_destroy(self, instance):
        exiger(self.request.user, instance, Niveau.WRITE)
        instance.mettre_a_la_corbeille(self.request.user)
        journaliser("FILE_DELETE", acteur=self.request.user, cible=instance)

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        fichier = self.get_object()
        exiger(request.user, fichier, Niveau.WRITE)
        cible = get_object_or_404(Folder, pk=request.data.get("target_folder"))
        exiger(request.user, cible, Niveau.WRITE)
        services.deplacer_fichier(fichier, cible, request.user)
        return Response(FileSerializer(fichier, context={"request": request}).data)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        fichier = self.get_object()
        exiger(request.user, fichier, Niveau.READ)
        if not fichier.current_version_id:
            raise Http404
        journaliser("FILE_DOWNLOAD", acteur=request.user, cible=fichier)
        url = stockage().url_temporaire(
            fichier.current_version.storage_key, fichier.name
        )
        if url:
            return Response({"url": url}, status=status.HTTP_200_OK)
        flux = stockage().flux(fichier.current_version.storage_key)
        reponse = StreamingHttpResponse(
            flux, content_type=fichier.mime_type or "application/octet-stream"
        )
        reponse["Content-Disposition"] = f'attachment; filename="{fichier.name}"'
        reponse["Content-Length"] = fichier.size_bytes
        return reponse

    @action(detail=True, methods=["get"])
    def versions(self, request, pk=None):
        fichier = self.get_object()
        return Response(
            FileVersionSerializer(fichier.versions.all(), many=True).data
        )

    @action(detail=True, methods=["post"], url_path=r"versions/(?P<numero>\d+)/restore")
    def restore_version(self, request, pk=None, numero=None):
        fichier = self.get_object()
        exiger(request.user, fichier, Niveau.WRITE)
        version = services.restaurer_version(fichier, int(numero), request.user)
        return Response(FileVersionSerializer(version).data)

    @action(detail=True, methods=["get", "put"])
    def metadata(self, request, pk=None):
        fichier = self.get_object()
        if request.method == "GET":
            return Response(
                FileMetadataSerializer(fichier.metadata.all(), many=True).data
            )
        exiger(request.user, fichier, Niveau.WRITE)
        for cle, valeur in (request.data or {}).items():
            FileMetadata.objects.update_or_create(
                file=fichier,
                key=cle,
                defaults={"value": str(valeur), "source": FileMetadata.Source.MANUEL},
            )
        return Response(FileMetadataSerializer(fichier.metadata.all(), many=True).data)

    @action(detail=True, methods=["get", "post"])
    def comments(self, request, pk=None):
        fichier = self.get_object()
        if request.method == "GET":
            return Response(
                CommentSerializer(
                    fichier.comments.filter(is_deleted=False), many=True
                ).data
            )
        exiger(request.user, fichier, Niveau.COMMENT)
        serializer = CommentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        commentaire = serializer.save(file=fichier, author=request.user)
        return Response(
            CommentSerializer(commentaire).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"])
    def lock(self, request, pk=None):
        fichier = self.get_object()
        exiger(request.user, fichier, Niveau.WRITE)
        fichier.verrouiller(request.user)
        return Response(FileSerializer(fichier, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def unlock(self, request, pk=None):
        fichier = self.get_object()
        if fichier.locked_by_id != request.user.id and not request.user.est_admin:
            raise OperationInvalide("Seul l'agent ayant pose le verrou peut le lever.")
        fichier.deverrouiller()
        return Response(FileSerializer(fichier, context={"request": request}).data)

    # -- edition dans l'application -------------------------------------
    @action(detail=True, methods=["get"])
    def contenu(self, request, pk=None):
        """Contenu a ouvrir dans l'editeur, et brouillon eventuel."""
        fichier = self.get_object()
        brouillon = edition.brouillon_de(fichier, request.user)
        return Response(
            {
                "editable": est_editable(fichier.name),
                "nom": fichier.name,
                "kind": fichier.kind,
                "version": (
                    fichier.current_version.version_number
                    if fichier.current_version_id
                    else 0
                ),
                "contenu": edition.lire_contenu(fichier),
                "brouillon": (
                    {
                        "contenu": brouillon.contenu,
                        "base_version": brouillon.base_version,
                        "enregistre_le": brouillon.derniere_frappe,
                    }
                    if brouillon
                    else None
                ),
                "modifiable": bool(
                    peut_ecrire(niveau_sur_fichier(request.user, fichier))
                ),
            }
        )

    @action(detail=True, methods=["put", "delete"])
    def brouillon(self, request, pk=None):
        """Sauvegarde automatique (PUT) ou abandon des modifications (DELETE)."""
        fichier = self.get_object()
        exiger(request.user, fichier, Niveau.WRITE)
        if request.method == "DELETE":
            edition.abandonner_brouillon(fichier, request.user)
            return Response(status=status.HTTP_204_NO_CONTENT)
        contenu = request.data.get("contenu")
        if contenu is None:
            raise OperationInvalide("Contenu absent.")
        return Response(edition.enregistrer_brouillon(fichier, request.user, contenu))

    @action(detail=True, methods=["post"], url_path="brouillon/publier")
    def publier_brouillon(self, request, pk=None):
        """Cree une version a partir du brouillon."""
        fichier = self.get_object()
        exiger(request.user, fichier, Niveau.WRITE)
        contenu = request.data.get("contenu")
        if contenu is not None:
            edition.enregistrer_brouillon(fichier, request.user, contenu)
        version = edition.publier_brouillon(
            fichier, request.user, commentaire=request.data.get("commentaire", "")
        )
        fichier.refresh_from_db()
        return Response(
            {
                "version": version.version_number,
                "fichier": FileSerializer(fichier, context={"request": request}).data,
            }
        )

    @action(detail=True, methods=["post"])
    def tags(self, request, pk=None):
        fichier = self.get_object()
        exiger(request.user, fichier, Niveau.WRITE)
        noms = request.data.get("tags", [])
        etiquettes = []
        for nom in noms:
            etiquette, _ = Tag.objects.get_or_create(
                name=nom.strip(), service=fichier.service
            )
            etiquettes.append(etiquette)
        fichier.tags.set(etiquettes)
        return Response(TagSerializer(fichier.tags.all(), many=True).data)


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class SimpleUploadView(APIView):
    """Televersement direct, pour les fichiers de petite taille."""

    def post(self, request):
        fichier_envoye = request.FILES.get("fichier")
        dossier_id = request.data.get("dossier")
        if not fichier_envoye or not dossier_id:
            raise OperationInvalide("Fichier et dossier sont requis.")
        if fichier_envoye.size > settings.SIMPLE_UPLOAD_MAX_MB * 1024 * 1024:
            raise OperationInvalide(
                "Utilisez le televersement fragmente pour ce volume "
                f"(> {settings.SIMPLE_UPLOAD_MAX_MB} Mo)."
            )
        dossier = get_object_or_404(Folder, pk=dossier_id)
        exiger(request.user, dossier, Niveau.WRITE)

        fichier, version = services.creer_ou_mettre_a_jour_fichier(
            nom=fichier_envoye.name,
            dossier=dossier,
            contenu=io.BytesIO(fichier_envoye.read()),
            auteur=request.user,
            commentaire=request.data.get("commentaire", ""),
        )
        from apps.geo.tasks import analyser_fichier

        analyser_fichier(str(fichier.id))
        return Response(
            FileSerializer(fichier, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(request=UploadInitSerializer, responses=OpenApiTypes.OBJECT)
class UploadInitView(APIView):
    """Ouvre un televersement fragmente.

    Le quota est verifie ici, avant tout transfert : sur une liaison de terrain,
    refuser apres 400 Mo envoyes serait inacceptable.
    """

    def post(self, request):
        serializer = UploadInitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        donnees = serializer.validated_data
        dossier = get_object_or_404(Folder, pk=donnees["dossier"])
        exiger(request.user, dossier, Niveau.WRITE)
        services.verifier_quota(dossier.service or request.user.service, donnees["taille"])

        taille_fragment = settings.UPLOAD_CHUNK_SIZE_MB * 1024 * 1024
        total = max(1, -(-donnees["taille"] // taille_fragment))
        session = UploadSession.objects.create(
            user=request.user,
            folder=dossier,
            filename=donnees["nom"],
            total_size=donnees["taille"],
            chunk_size=taille_fragment,
            total_chunks=total,
            checksum_sha256=donnees.get("checksum_sha256", ""),
            comment=donnees.get("commentaire", ""),
            client_id=donnees.get("client_id"),
        )
        return Response(
            {
                "upload_id": str(session.id),
                "chunk_size": taille_fragment,
                "total_chunks": total,
                "fragments_manquants": session.manquants,
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class UploadPartView(APIView):
    def put(self, request, upload_id, numero):
        session = get_object_or_404(
            UploadSession, pk=upload_id, user=request.user, status=UploadSession.Statut.EN_COURS
        )
        numero = int(numero)
        if not 1 <= numero <= session.total_chunks:
            raise OperationInvalide("Numero de fragment hors limites.")
        donnees = request.body or (
            request.FILES["fragment"].read() if "fragment" in request.FILES else b""
        )
        if not donnees:
            raise OperationInvalide("Fragment vide.")
        stockage().ecrire(f"_uploads/{session.id}/{numero:06d}", io.BytesIO(donnees))
        if numero not in session.received_chunks:
            session.received_chunks = sorted(set(session.received_chunks + [numero]))
            session.save(update_fields=["received_chunks", "updated_at"])
        return Response(
            {"recus": len(session.received_chunks), "manquants": session.manquants}
        )


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class UploadCompleteView(APIView):
    def post(self, request, upload_id):
        session = get_object_or_404(UploadSession, pk=upload_id, user=request.user)
        if session.status == UploadSession.Statut.TERMINE and session.file_id:
            # Idempotence : rejouer un `complete` ne cree pas de doublon.
            return Response(
                FileSerializer(session.file, context={"request": request}).data
            )
        if not session.complet:
            raise OperationInvalide(
                f"Fragments manquants : {session.manquants[:20]}"
            )
        assemblage = io.BytesIO()
        for numero in range(1, session.total_chunks + 1):
            with stockage().lire(f"_uploads/{session.id}/{numero:06d}") as fragment:
                assemblage.write(fragment.read())
        assemblage.seek(0)

        if session.checksum_sha256:
            if sha256_flux(assemblage) != session.checksum_sha256.lower():
                raise ChecksumInvalide()

        fichier, version = services.creer_ou_mettre_a_jour_fichier(
            nom=session.filename,
            dossier=session.folder,
            contenu=assemblage,
            auteur=request.user,
            commentaire=session.comment,
            client_id=session.client_id,
        )
        session.status = UploadSession.Statut.TERMINE
        session.file = fichier
        session.save(update_fields=["status", "file", "updated_at"])
        for numero in range(1, session.total_chunks + 1):
            try:
                stockage().supprimer(f"_uploads/{session.id}/{numero:06d}")
            except Exception:  # pragma: no cover
                pass
        from apps.geo.tasks import analyser_fichier

        analyser_fichier(str(fichier.id))
        return Response(
            FileSerializer(fichier, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class NouveauDocumentView(APIView):
    """Cree un document vide, modifiable immediatement dans l'application."""

    def post(self, request):
        dossier = get_object_or_404(Folder, pk=request.data.get("dossier"))
        exiger(request.user, dossier, Niveau.WRITE)
        nom = (request.data.get("nom") or "").strip()
        if not nom:
            raise OperationInvalide("Le nom du document est requis.")
        fichier = edition.creer_document(
            nom=nom,
            dossier=dossier,
            auteur=request.user,
            contenu=request.data.get("contenu", ""),
            croquis=bool(request.data.get("croquis")),
        )
        return Response(
            FileSerializer(fichier, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class TrashView(APIView):
    def get(self, request):
        dossiers = Folder.objects.filter(is_deleted=True)
        fichiers = File.objects.filter(is_deleted=True)
        if not request.user.est_admin:
            dossiers = dossiers.filter(
                Q(owner=request.user) | Q(service=request.user.service)
            )
            fichiers = fichiers.filter(
                Q(owner=request.user) | Q(service=request.user.service)
            )
        return Response(
            {
                "dossiers": FolderSerializer(
                    dossiers, many=True, context={"request": request}
                ).data,
                "fichiers": FileSerializer(
                    fichiers, many=True, context={"request": request}
                ).data,
            }
        )


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class TrashItemView(APIView):
    def _obtenir(self, identifiant):
        dossier = Folder.objects.filter(pk=identifiant, is_deleted=True).first()
        if dossier:
            return dossier
        fichier = File.objects.filter(pk=identifiant, is_deleted=True).first()
        if fichier:
            return fichier
        raise Http404

    def post(self, request, identifiant):
        element = self._obtenir(identifiant)
        if isinstance(element, Folder):
            exiger(request.user, element.parent or element, Niveau.WRITE)
            element.restaurer()
            journaliser("FOLDER_RESTORE", acteur=request.user, cible=element)
        else:
            exiger(request.user, element.folder, Niveau.WRITE)
            element.restaurer()
            journaliser("FILE_RESTORE", acteur=request.user, cible=element)
        return Response({"detail": "Element restaure."})

    def delete(self, request, identifiant):
        """Purge definitive : c'est la seule operation de la plateforme qui
        detruit reellement des donnees. Elle libere aussi les objets binaires,
        sans quoi l'espace disque ne serait jamais recupere."""
        if not request.user.est_admin:
            raise OperationInvalide("Seul un administrateur peut purger definitivement.")
        element = self._obtenir(identifiant)
        chemin = getattr(element, "chemin_complet", None) or element.path

        if isinstance(element, File):
            fichiers = [element]
        else:
            # Tout le sous-arbre part avec le dossier.
            fichiers = list(
                File.objects.filter(folder__path__startswith=element.path)
            )

        for fichier in fichiers:
            _liberer_objets(fichier)

        nombre = len(fichiers)
        element.delete()
        journaliser(
            "TRASH_PURGE",
            acteur=request.user,
            target_type="NODE",
            target_path=chemin,
            fichiers_purges=nombre,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


def _liberer_objets(fichier: File) -> None:
    """Supprime les versions d'un fichier et les objets binaires devenus
    orphelins. Un objet partage par deduplication n'est efface que lorsque
    plus aucune version ne le reference."""
    for version in fichier.versions.all():
        cle = version.storage_key
        version.delete()
        if not FileVersion.objects.filter(storage_key=cle).exists():
            try:
                stockage().supprimer(cle)
            except Exception:  # pragma: no cover - objet deja absent
                pass
