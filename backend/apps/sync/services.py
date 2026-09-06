"""Moteur de synchronisation hors ligne.

Regle directrice, qui prime sur toutes les autres : **une synchronisation ne
detruit jamais un travail de terrain.** En cas de doute, on conserve les deux
versions et on demande l'arbitrage.

Les identifiants des noeuds crees hors ligne sont generes par le client (UUID
v4) et acceptes tels quels : aucune reecriture d'identifiant n'est necessaire
au retour du reseau, ce qui evite toute une classe de bugs de reconciliation.
"""

from __future__ import annotations

import base64
import io

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.audit.services import journaliser
from apps.common.exceptions import OperationInvalide
from apps.notifications.services import notifier
from apps.sharing.models import Niveau
from apps.sharing.services import peut
from apps.storage import services as storage_services
from apps.storage.models import File, FileMetadata, Folder, Origine

from .models import Resolution, StatutOperation, SyncOperation, TypeOperation


class ResultatOperation(dict):
    pass


def _refuser(operation: SyncOperation, motif: str) -> ResultatOperation:
    operation.status = StatutOperation.REJECTED
    operation.error = motif
    operation.save(update_fields=["status", "error", "updated_at"])
    return ResultatOperation(id=str(operation.id), status=operation.status, error=motif)


def _appliquer_creation_dossier(operation: SyncOperation, utilisateur):
    charge = operation.payload
    parent = Folder.objects.filter(pk=charge.get("parent")).first()
    if parent is None:
        return _refuser(operation, "Dossier parent introuvable ou supprime.")
    if not peut(utilisateur, parent, Niveau.WRITE):
        return _refuser(operation, "Droit d'ecriture perdu sur le dossier parent.")

    existant = Folder.objects.filter(pk=operation.target_id).first()
    if existant is not None:
        # Rejeu d'une operation deja appliquee : l'idempotence est acquise.
        return _succes(operation, {"folder": str(existant.id)})

    nom = storage_services.nom_disponible(
        charge.get("name", "Nouveau dossier"), dossier=parent, modele=Folder
    )
    dossier = storage_services.creer_dossier(
        nom=nom, parent=parent, auteur=utilisateur, identifiant=operation.target_id
    )
    return _succes(operation, {"folder": str(dossier.id), "name": dossier.name})


def _appliquer_renommage(operation: SyncOperation, utilisateur):
    nouveau_nom = operation.payload.get("name", "")
    if operation.target_type == "FOLDER":
        dossier = Folder.objects.filter(pk=operation.target_id, is_deleted=False).first()
        if dossier is None:
            return _refuser(operation, "Dossier introuvable.")
        if not peut(utilisateur, dossier, Niveau.WRITE):
            return _refuser(operation, "Droit d'ecriture perdu.")
        # Renommage concurrent : l'horodatage serveur le plus recent l'emporte,
        # l'autre nom reste consultable dans le journal.
        if dossier.updated_at > operation.client_timestamp:
            journaliser(
                "SYNC_CONFLICT", acteur=utilisateur, cible=dossier,
                type="renommage", nom_ecarte=nouveau_nom,
            )
            return _conflit(operation, Resolution.SERVER_WINS, "Renomme entre-temps.")
        dossier.name = storage_services.nom_disponible(
            nouveau_nom, dossier=dossier.parent, modele=Folder, exclure=dossier.pk
        )
        dossier.save()
        return _succes(operation, {"name": dossier.name})

    fichier = File.objects.filter(pk=operation.target_id, is_deleted=False).first()
    if fichier is None:
        return _refuser(operation, "Fichier introuvable.")
    if not peut(utilisateur, fichier, Niveau.WRITE):
        return _refuser(operation, "Droit d'ecriture perdu.")
    fichier.name = storage_services.nom_disponible(
        nouveau_nom, dossier=fichier.folder, modele=File, exclure=fichier.pk
    )
    fichier.save(update_fields=["name", "updated_at"])
    return _succes(operation, {"name": fichier.name})


def _appliquer_deplacement(operation: SyncOperation, utilisateur):
    cible = Folder.objects.filter(
        pk=operation.payload.get("target_folder"), is_deleted=False
    ).first()
    if cible is None:
        # Dossier de destination supprime entre-temps : on ne perd rien, on
        # range l'element dans « Elements non classes » de l'agent.
        cible = _dossier_non_classes(utilisateur)
        if cible is None:
            return _refuser(operation, "Dossier de destination supprime.")

    if operation.target_type == "FOLDER":
        dossier = Folder.objects.filter(pk=operation.target_id, is_deleted=False).first()
        if dossier is None:
            return _refuser(operation, "Dossier introuvable.")
        if not (peut(utilisateur, dossier, Niveau.WRITE) and peut(utilisateur, cible, Niveau.WRITE)):
            return _refuser(operation, "Droits insuffisants pour ce deplacement.")
        dossier.name = storage_services.nom_disponible(
            dossier.name, dossier=cible, modele=Folder, exclure=dossier.pk
        )
        storage_services.deplacer_dossier(dossier, cible, utilisateur)
        return _succes(operation, {"parent": str(cible.id)})

    fichier = File.objects.filter(pk=operation.target_id, is_deleted=False).first()
    if fichier is None:
        return _refuser(operation, "Fichier introuvable.")
    if not (peut(utilisateur, fichier, Niveau.WRITE) and peut(utilisateur, cible, Niveau.WRITE)):
        return _refuser(operation, "Droits insuffisants pour ce deplacement.")
    fichier.name = storage_services.nom_disponible(
        fichier.name, dossier=cible, modele=File, exclure=fichier.pk
    )
    storage_services.deplacer_fichier(fichier, cible, utilisateur)
    return _succes(operation, {"folder": str(cible.id)})


def _appliquer_version(operation: SyncOperation, utilisateur):
    """Nouvelle version produite hors ligne.

    C'est ici que se joue la promesse de non-destruction : si le fichier a
    change sur le serveur depuis la derniere synchronisation de l'appareil, la
    version serveur reste courante et la version de terrain est empilee comme
    copie de conflit, notifiee a son auteur. Aucun octet n'est perdu.
    """
    charge = operation.payload
    contenu = charge.get("contenu_base64")
    if not contenu:
        return _refuser(operation, "Contenu absent de l'operation.")
    donnees = io.BytesIO(base64.b64decode(contenu))

    fichier = File.objects.filter(pk=operation.target_id).first()
    if fichier is None:
        dossier = Folder.objects.filter(pk=charge.get("folder"), is_deleted=False).first()
        if dossier is None:
            return _refuser(operation, "Dossier introuvable.")
        if not peut(utilisateur, dossier, Niveau.WRITE):
            return _refuser(operation, "Droit d'ecriture perdu.")
        nom = storage_services.nom_disponible(
            charge.get("name", "sans-nom"), dossier=dossier, modele=File
        )
        fichier, _ = storage_services.creer_ou_mettre_a_jour_fichier(
            nom=nom,
            dossier=dossier,
            contenu=donnees,
            auteur=utilisateur,
            commentaire=charge.get("commentaire", "Cree hors ligne"),
            origine=Origine.SYNC_OFFLINE,
            client_id=operation.id,
            identifiant=operation.target_id,
        )
        return _succes(operation, {"file": str(fichier.id), "name": fichier.name})

    if not peut(utilisateur, fichier, Niveau.WRITE):
        return _refuser(operation, "Droit d'ecriture perdu sur ce fichier.")

    if fichier.is_deleted:
        # Supprime cote serveur, modifie hors ligne : on restaure et on signale.
        fichier.restaurer()
        journaliser("SYNC_CONFLICT", acteur=utilisateur, cible=fichier,
                    type="supprime_puis_modifie")

    version_serveur = (
        fichier.current_version.version_number if fichier.current_version_id else 0
    )
    en_conflit = (
        operation.base_version is not None and operation.base_version < version_serveur
    )

    fichier, version = storage_services.creer_ou_mettre_a_jour_fichier(
        nom=fichier.name,
        dossier=fichier.folder,
        contenu=donnees,
        auteur=utilisateur,
        commentaire=charge.get("commentaire", "Modifie hors ligne"),
        origine=Origine.SYNC_OFFLINE,
        client_id=operation.id,
        fichier_existant=fichier,
    )

    if en_conflit:
        version.is_conflict_copy = True
        version.comment = (
            f"Copie de conflit : modifiee hors ligne a partir de la version "
            f"{operation.base_version}, alors que le serveur etait en version "
            f"{version_serveur}."
        )
        version.save(update_fields=["is_conflict_copy", "comment", "updated_at"])
        journaliser("SYNC_CONFLICT", acteur=utilisateur, cible=fichier,
                    base_version=operation.base_version, version_serveur=version_serveur)
        notifier(
            utilisateur,
            "CONFLIT_SYNC",
            titre=f"Conflit sur « {fichier.name} »",
            corps=(
                "Votre modification hors ligne a ete conservee comme version "
                f"{version.version_number}. Les deux versions sont disponibles "
                "dans l'historique du fichier."
            ),
            cible=fichier,
        )
        operation.status = StatutOperation.CONFLICT
        operation.conflict_resolution = Resolution.BOTH_KEPT
        operation.applied_at = timezone.now()
        operation.result = {"file": str(fichier.id), "version": version.version_number}
        operation.save(
            update_fields=["status", "conflict_resolution", "applied_at", "result", "updated_at"]
        )
        return ResultatOperation(
            id=str(operation.id),
            status=operation.status,
            resolution=operation.conflict_resolution,
            **operation.result,
        )

    return _succes(operation, {"file": str(fichier.id), "version": version.version_number})


def _appliquer_suppression(operation: SyncOperation, utilisateur):
    modele = Folder if operation.target_type == "FOLDER" else File
    element = modele.objects.filter(pk=operation.target_id).first()
    if element is None:
        return _succes(operation, {"deja_supprime": True})
    if not peut(utilisateur, element, Niveau.WRITE):
        return _refuser(operation, "Droit d'ecriture perdu.")
    element.mettre_a_la_corbeille(utilisateur)
    return _succes(operation, {"supprime": True})


def _appliquer_restauration(operation: SyncOperation, utilisateur):
    modele = Folder if operation.target_type == "FOLDER" else File
    element = modele.objects.filter(pk=operation.target_id).first()
    if element is None:
        return _refuser(operation, "Element introuvable.")
    element.restaurer()
    return _succes(operation, {"restaure": True})


def _appliquer_metadonnees(operation: SyncOperation, utilisateur):
    fichier = File.objects.filter(pk=operation.target_id).first()
    if fichier is None:
        return _refuser(operation, "Fichier introuvable.")
    if not peut(utilisateur, fichier, Niveau.WRITE):
        return _refuser(operation, "Droit d'ecriture perdu.")
    for cle, valeur in (operation.payload.get("metadata") or {}).items():
        FileMetadata.objects.update_or_create(
            file=fichier, key=cle,
            defaults={"value": str(valeur), "source": FileMetadata.Source.MANUEL},
        )
    return _succes(operation, {"metadata": True})


def _dossier_non_classes(utilisateur):
    racine = Folder.objects.filter(
        is_service_root=True, service=utilisateur.service, is_deleted=False
    ).first()
    if racine is None:
        return None
    dossier, _ = Folder.objects.get_or_create(
        parent=racine,
        name="Elements non classes",
        is_deleted=False,
        defaults={"owner": utilisateur, "service": utilisateur.service},
    )
    return dossier


def _succes(operation: SyncOperation, resultat: dict) -> ResultatOperation:
    operation.status = StatutOperation.APPLIED
    operation.applied_at = timezone.now()
    operation.result = resultat
    operation.save(update_fields=["status", "applied_at", "result", "updated_at"])
    return ResultatOperation(id=str(operation.id), status=operation.status, **resultat)


def _conflit(operation: SyncOperation, resolution: str, message: str) -> ResultatOperation:
    operation.status = StatutOperation.CONFLICT
    operation.conflict_resolution = resolution
    operation.error = message
    operation.save(
        update_fields=["status", "conflict_resolution", "error", "updated_at"]
    )
    return ResultatOperation(
        id=str(operation.id), status=operation.status, resolution=resolution, detail=message
    )


HANDLERS = {
    TypeOperation.CREATE_FOLDER: _appliquer_creation_dossier,
    TypeOperation.RENAME: _appliquer_renommage,
    TypeOperation.MOVE: _appliquer_deplacement,
    TypeOperation.UPLOAD_VERSION: _appliquer_version,
    TypeOperation.DELETE: _appliquer_suppression,
    TypeOperation.RESTORE: _appliquer_restauration,
    TypeOperation.SET_METADATA: _appliquer_metadonnees,
}


def appliquer_lot(operations_brutes: list[dict], utilisateur, device) -> list[dict]:
    """Applique un lot d'operations dans l'ordre `client_seq`.

    Chaque operation est traitee dans sa propre transaction : un echec isole ne
    fait pas perdre le reste du travail de terrain.
    """
    resultats = []
    for brute in sorted(operations_brutes, key=lambda o: o.get("client_seq", 0)):
        identifiant = brute.get("id")
        existante = SyncOperation.objects.filter(pk=identifiant).first()
        if existante and existante.status != StatutOperation.PENDING:
            resultats.append(
                {
                    "id": str(existante.id),
                    "status": existante.status,
                    "rejeu": True,
                    **(existante.result or {}),
                }
            )
            continue

        operation = existante or SyncOperation(
            id=identifiant,
            device=device,
            user=utilisateur,
            op_type=brute["op_type"],
            target_type=brute["target_type"],
            target_id=brute["target_id"],
            payload=brute.get("payload", {}),
            client_seq=brute.get("client_seq", 0),
            base_version=brute.get("base_version"),
            client_timestamp=brute.get("client_timestamp") or timezone.now(),
        )
        operation.save()

        handler = HANDLERS.get(operation.op_type)
        if handler is None:
            resultats.append(_refuser(operation, "Type d'operation inconnu."))
            continue
        try:
            with transaction.atomic():
                resultats.append(handler(operation, utilisateur))
        except OperationInvalide as erreur:
            resultats.append(_refuser(operation, str(erreur.detail)))
        except Exception as erreur:  # pragma: no cover
            resultats.append(_refuser(operation, str(erreur)[:500]))
    return resultats
