"""Operations metier sur les dossiers et fichiers."""

from __future__ import annotations

import io
import re
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Max, Sum

from apps.audit.services import journaliser
from apps.common import mime as mime_utils
from apps.common.exceptions import (
    ChecksumInvalide,
    ConflitDeNom,
    FichierVerrouille,
    OperationInvalide,
    QuotaDepasse,
)
from apps.common.object_storage import cle_objet, sha256_flux, stockage

from .models import File, FileVersion, Folder, Kind, Origine, nettoyer_nom


# ---------------------------------------------------------------------------
# Noms
# ---------------------------------------------------------------------------
def nom_disponible(nom: str, *, dossier: Folder, modele, exclure=None) -> str:
    """Renvoie un nom libre dans le dossier, en suffixant « (2) », « (3) »...

    Utilise a la synchronisation : une creation hors ligne ne doit jamais
    echouer pour un simple conflit de nom.
    """
    nom = nettoyer_nom(nom)
    champ = "folder" if modele is File else "parent"
    base = File.objects if modele is File else Folder.objects
    requete = base.filter(**{champ: dossier}, is_deleted=False)
    if exclure is not None:
        requete = requete.exclude(pk=exclure)
    existants = set(requete.values_list("name", flat=True))
    if nom not in existants:
        return nom
    tige, extension = (Path(nom).stem, Path(nom).suffix) if modele is File else (nom, "")
    tige = re.sub(r" \(\d+\)$", "", tige)
    for index in range(2, 1000):
        candidat = f"{tige} ({index}){extension}"
        if candidat not in existants:
            return candidat
    raise ConflitDeNom()


def verifier_nom_libre(nom: str, *, dossier: Folder, modele, exclure=None):
    champ = "folder" if modele is File else "parent"
    base = File.objects if modele is File else Folder.objects
    requete = base.filter(**{champ: dossier}, name=nettoyer_nom(nom), is_deleted=False)
    if exclure is not None:
        requete = requete.exclude(pk=exclure)
    if requete.exists():
        raise ConflitDeNom()


# ---------------------------------------------------------------------------
# Quotas
# ---------------------------------------------------------------------------
def usage_service(service) -> int:
    if service is None:
        return 0
    return (
        FileVersion.objects.filter(file__service=service).aggregate(
            total=Sum("size_bytes")
        )["total"]
        or 0
    )


def verifier_quota(service, taille_ajoutee: int):
    """Verifie *avant* tout transfert : sur une liaison lente, refuser apres
    avoir envoye 400 Mo serait inacceptable."""
    if service is None:
        return
    quota = service.quota_effectif
    if usage_service(service) + taille_ajoutee > quota:
        raise QuotaDepasse(
            contexte={"quota_octets": quota, "usage_octets": usage_service(service)}
        )


# ---------------------------------------------------------------------------
# Dossiers
# ---------------------------------------------------------------------------
@transaction.atomic
def creer_dossier(
    *, nom, parent, auteur, service=None, identifiant=None, est_racine_service=False
) -> Folder:
    """Cree un dossier. `parent=None` cree un espace racine de service."""
    verifier_nom_libre(nom, dossier=parent, modele=Folder)
    dossier = Folder(
        name=nom,
        parent=parent,
        owner=auteur,
        service=service or (parent.service if parent else auteur.service),
        is_service_root=est_racine_service,
    )
    if identifiant:
        dossier.id = identifiant
    dossier.save()
    journaliser("FOLDER_CREATE", acteur=auteur, cible=dossier)
    return dossier


@transaction.atomic
def deplacer_dossier(dossier: Folder, nouveau_parent: Folder, auteur) -> Folder:
    if nouveau_parent.path.startswith(dossier.path):
        raise OperationInvalide("Un dossier ne peut pas etre deplace dans lui-meme.")
    verifier_nom_libre(dossier.name, dossier=nouveau_parent, modele=Folder, exclure=dossier.pk)
    ancien = dossier.path
    dossier.parent = nouveau_parent
    dossier.service = nouveau_parent.service or dossier.service
    dossier.save()
    journaliser("FOLDER_MOVE", acteur=auteur, cible=dossier, ancien_chemin=ancien)
    return dossier


@transaction.atomic
def renommer_dossier(dossier: Folder, nouveau_nom: str, auteur) -> Folder:
    verifier_nom_libre(nouveau_nom, dossier=dossier.parent, modele=Folder, exclure=dossier.pk)
    ancien = dossier.name
    dossier.name = nouveau_nom
    dossier.save()
    journaliser("FOLDER_RENAME", acteur=auteur, cible=dossier, ancien_nom=ancien)
    return dossier


# ---------------------------------------------------------------------------
# Fichiers et versions
# ---------------------------------------------------------------------------
def _analyser(contenu: io.BytesIO, nom: str) -> tuple[str, str]:
    entete = contenu.read(512)
    contenu.seek(0)
    if mime_utils.est_executable(entete):
        raise OperationInvalide(
            "Les fichiers executables ne sont pas acceptes sur la plateforme."
        )
    type_mime = mime_utils.detecter_mime(entete, nom)
    return type_mime, mime_utils.deduire_kind(type_mime, nom)


@transaction.atomic
def creer_ou_mettre_a_jour_fichier(
    *,
    nom: str,
    dossier: Folder,
    contenu,
    auteur,
    commentaire: str = "",
    origine: str = Origine.WEB,
    client_id=None,
    identifiant=None,
    checksum_attendu: str = "",
    fichier_existant: File | None = None,
) -> tuple[File, FileVersion]:
    """Cree un fichier ou ajoute une version a un fichier existant.

    Une modification n'ecrase jamais le contenu precedent : elle empile une
    nouvelle version. La deduplication par SHA-256 evite de stocker deux fois
    un contenu identique.
    """
    nom = nettoyer_nom(nom)
    if not hasattr(contenu, "read"):
        contenu = io.BytesIO(contenu)

    contenu.seek(0, 2)
    taille = contenu.tell()
    contenu.seek(0)
    if taille > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise OperationInvalide(
            f"Fichier trop volumineux (maximum {settings.MAX_UPLOAD_SIZE_MB} Mo)."
        )

    checksum = sha256_flux(contenu)
    if checksum_attendu and checksum_attendu.lower() != checksum:
        raise ChecksumInvalide()

    type_mime, kind = _analyser(contenu, nom)
    service = dossier.service or auteur.service
    verifier_quota(service, taille)

    fichier = fichier_existant
    if fichier is None:
        fichier = File.objects.filter(
            folder=dossier, name=nom, is_deleted=False
        ).first()

    if fichier is None:
        fichier = File(
            name=nom,
            folder=dossier,
            owner=auteur,
            service=service,
            mime_type=type_mime,
            kind=kind,
            size_bytes=taille,
        )
        if identifiant:
            fichier.id = identifiant
        fichier.save()
        numero = 1
    else:
        if fichier.is_locked and fichier.locked_by_id not in (None, auteur.id):
            raise FichierVerrouille()
        numero = (
            fichier.versions.aggregate(m=Max("version_number"))["m"] or 0
        ) + 1

    cle = cle_objet(service.code if service else "", fichier.id, numero, nom)

    # Deduplication : si ce contenu exact existe deja, on reutilise son objet.
    jumelle = FileVersion.objects.filter(checksum_sha256=checksum).first()
    if jumelle and stockage().existe(jumelle.storage_key):
        cle = jumelle.storage_key
    else:
        stockage().ecrire(cle, contenu)

    version = FileVersion.objects.create(
        file=fichier,
        version_number=numero,
        storage_key=cle,
        size_bytes=taille,
        checksum_sha256=checksum,
        mime_type=type_mime,
        uploaded_by=auteur,
        comment=commentaire,
        origin=origine,
        client_id=client_id,
    )
    fichier.current_version = version
    fichier.size_bytes = taille
    fichier.mime_type = type_mime
    fichier.kind = kind
    fichier.save(
        update_fields=["current_version", "size_bytes", "mime_type", "kind", "updated_at"]
    )

    journaliser(
        "FILE_UPLOAD",
        acteur=auteur,
        cible=fichier,
        version=numero,
        taille=taille,
        origine=origine,
    )
    purger_anciennes_versions(fichier)
    return fichier, version


def purger_anciennes_versions(fichier: File):
    """Rétention : on garde les N dernières versions, jamais la courante."""
    limite = settings.VERSION_RETENTION_COUNT
    versions = list(fichier.versions.order_by("-version_number"))
    if len(versions) <= limite:
        return
    for version in versions[limite:]:
        if fichier.current_version_id == version.id:
            continue
        cle = version.storage_key
        version.delete()
        if not FileVersion.objects.filter(storage_key=cle).exists():
            try:
                stockage().supprimer(cle)
            except Exception:  # pragma: no cover
                pass


@transaction.atomic
def restaurer_version(fichier: File, numero: int, auteur) -> FileVersion:
    """Restaurer, c'est empiler une nouvelle version identique a l'ancienne :
    l'historique reste lineaire et rien n'est perdu."""
    ancienne = fichier.versions.filter(version_number=numero).first()
    if ancienne is None:
        raise OperationInvalide("Cette version n'existe pas.")
    nouveau_numero = (
        fichier.versions.aggregate(m=Max("version_number"))["m"] or 0
    ) + 1
    version = FileVersion.objects.create(
        file=fichier,
        version_number=nouveau_numero,
        storage_key=ancienne.storage_key,
        size_bytes=ancienne.size_bytes,
        checksum_sha256=ancienne.checksum_sha256,
        mime_type=ancienne.mime_type,
        uploaded_by=auteur,
        comment=f"Restauration de la version {numero}",
        origin=Origine.WEB,
    )
    fichier.current_version = version
    fichier.size_bytes = version.size_bytes
    fichier.save(update_fields=["current_version", "size_bytes", "updated_at"])
    journaliser("VERSION_RESTORE", acteur=auteur, cible=fichier, version_source=numero)
    return version


@transaction.atomic
def deplacer_fichier(fichier: File, dossier: Folder, auteur) -> File:
    verifier_nom_libre(fichier.name, dossier=dossier, modele=File, exclure=fichier.pk)
    ancien = fichier.chemin_complet
    fichier.folder = dossier
    fichier.service = dossier.service or fichier.service
    fichier.save(update_fields=["folder", "service", "updated_at"])
    journaliser("FILE_MOVE", acteur=auteur, cible=fichier, ancien_chemin=ancien)
    return fichier


@transaction.atomic
def renommer_fichier(fichier: File, nouveau_nom: str, auteur) -> File:
    verifier_nom_libre(nouveau_nom, dossier=fichier.folder, modele=File, exclure=fichier.pk)
    ancien = fichier.name
    fichier.name = nouveau_nom
    fichier.save(update_fields=["name", "updated_at"])
    journaliser("FILE_RENAME", acteur=auteur, cible=fichier, ancien_nom=ancien)
    return fichier
