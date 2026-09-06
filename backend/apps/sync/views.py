from __future__ import annotations

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView

from apps.accounts.models import Device
from apps.common.exceptions import OperationInvalide
from apps.sharing.services import dossiers_visibles, fichiers_visibles
from apps.storage.models import File, Folder
from apps.storage.serializers import FileSerializer, FolderSerializer

from .models import ChangeLog, StatutOperation, SyncOperation
from .serializers import LotOperationsSerializer, SyncOperationSerializer
from .services import appliquer_lot

TAILLE_LOT_DELTA = 200


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class DeltaView(APIView):
    """Changements survenus depuis le curseur de l'appareil.

    Le client ne transmet qu'un entier (`seq`) : aucune horloge a synchroniser,
    aucune fenetre temporelle a recouvrir, et un appareil reste au bureau
    pendant trois semaines rattrape exactement ce qu'il a manque.
    """

    def get(self, request):
        curseur = int(request.query_params.get("cursor", 0))
        portee = request.query_params.get("scope")

        chemins_visibles = list(
            dossiers_visibles(request.user).values_list("path", flat=True)
        )
        requete = ChangeLog.objects.filter(seq__gt=curseur)
        if portee:
            dossier = get_object_or_404(Folder, pk=portee)
            requete = requete.filter(folder_path__startswith=dossier.path)
        if not (request.user.est_admin or request.user.est_directeur):
            condition = Q(pk__in=[])
            for chemin in chemins_visibles:
                condition |= Q(folder_path__startswith=chemin)
            requete = requete.filter(condition)

        changements = list(requete.order_by("seq")[:TAILLE_LOT_DELTA])
        nouveau_curseur = changements[-1].seq if changements else curseur

        device_id = request.query_params.get("device")
        if device_id:
            Device.objects.filter(pk=device_id, user=request.user).update(
                sync_cursor=nouveau_curseur, last_sync_at=timezone.now()
            )

        return Response(
            {
                "cursor": nouveau_curseur,
                "reste": requete.filter(seq__gt=nouveau_curseur).exists(),
                "changements": [
                    {
                        "seq": c.seq,
                        "entity_type": c.entity_type,
                        "entity_id": str(c.entity_id),
                        "change_type": c.change_type,
                        "folder_path": c.folder_path,
                        "payload": c.payload,
                        "created_at": c.created_at,
                    }
                    for c in changements
                ],
            }
        )


@extend_schema(request=LotOperationsSerializer, responses=OpenApiTypes.OBJECT)
class OperationsView(APIView):
    """Reception d'un lot d'operations produites hors ligne."""

    def post(self, request):
        serializer = LotOperationsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device = get_object_or_404(
            Device, pk=serializer.validated_data["device"], user=request.user
        )
        if device.is_revoked:
            raise OperationInvalide(
                "Cet appareil a ete revoque. Reenregistrez-le pour synchroniser."
            )
        resultats = appliquer_lot(
            serializer.validated_data["operations"], request.user, device
        )
        device.last_sync_at = timezone.now()
        device.save(update_fields=["last_sync_at", "updated_at"])
        return Response({"resultats": resultats}, status=status.HTTP_200_OK)


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class OperationDetailView(APIView):
    def get(self, request, pk):
        operation = get_object_or_404(SyncOperation, pk=pk, user=request.user)
        return Response(SyncOperationSerializer(operation).data)


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class ConflitsView(APIView):
    def get(self, request):
        conflits = SyncOperation.objects.filter(
            user=request.user, status=StatutOperation.CONFLICT
        )
        return Response(SyncOperationSerializer(conflits, many=True).data)


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class ResoudreConflitView(APIView):
    def post(self, request, pk):
        operation = get_object_or_404(
            SyncOperation, pk=pk, user=request.user, status=StatutOperation.CONFLICT
        )
        resolution = request.data.get("resolution")
        if resolution not in ("SERVER_WINS", "CLIENT_WINS", "BOTH_KEPT"):
            raise OperationInvalide("Resolution inconnue.")

        if resolution == "CLIENT_WINS" and operation.result.get("file"):
            fichier = File.objects.filter(pk=operation.result["file"]).first()
            version = (
                fichier.versions.filter(
                    version_number=operation.result.get("version")
                ).first()
                if fichier
                else None
            )
            if fichier and version:
                fichier.current_version = version
                fichier.size_bytes = version.size_bytes
                fichier.save(update_fields=["current_version", "size_bytes", "updated_at"])
                version.is_conflict_copy = False
                version.save(update_fields=["is_conflict_copy", "updated_at"])

        operation.conflict_resolution = resolution
        operation.status = StatutOperation.APPLIED
        operation.save(update_fields=["conflict_resolution", "status", "updated_at"])
        return Response(SyncOperationSerializer(operation).data)


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class ManifestView(APIView):
    """Empreinte du perimetre : permet au client de verifier son cache local
    sans retelecharger le moindre octet."""

    def get(self, request):
        portee = request.query_params.get("scope")
        fichiers = fichiers_visibles(request.user).select_related("current_version")
        if portee:
            dossier = get_object_or_404(Folder, pk=portee)
            fichiers = fichiers.filter(folder__path__startswith=dossier.path)
        return Response(
            {
                "genere_le": timezone.now(),
                "fichiers": [
                    {
                        "id": str(f.id),
                        "name": f.name,
                        "folder": str(f.folder_id),
                        "version": (
                            f.current_version.version_number if f.current_version_id else 0
                        ),
                        "checksum": (
                            f.current_version.checksum_sha256 if f.current_version_id else ""
                        ),
                        "size": f.size_bytes,
                        "updated_at": f.updated_at,
                    }
                    for f in fichiers[:5000]
                ],
            }
        )
