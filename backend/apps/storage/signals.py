"""Alimentation du journal de changements (delta de synchronisation).

Chaque creation, modification ou suppression d'un noeud ecrit une ligne dans
`sync.ChangeLog`. Le client hors ligne ne demande ensuite que
`seq > son_curseur` : pas d'horloge a synchroniser, pas de fenetre a recouvrir.
"""

from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.audit.middleware import requete_courante

from .models import File, Folder


def _acteur():
    request = requete_courante()
    if request is None:
        return None
    utilisateur = getattr(request, "user", None)
    if utilisateur is not None and utilisateur.is_authenticated:
        return utilisateur
    return None


def enregistrer_changement(entite, type_changement: str, **payload):
    from apps.sync.models import ChangeLog

    if isinstance(entite, Folder):
        type_entite, chemin = "FOLDER", entite.path
    else:
        type_entite, chemin = "FILE", entite.folder.path

    ChangeLog.objects.create(
        entity_type=type_entite,
        entity_id=entite.id,
        change_type=type_changement,
        service=entite.service,
        folder_path=chemin,
        payload=payload,
        actor=_acteur(),
    )


@receiver(post_save, sender=Folder)
def dossier_modifie(sender, instance, created, **kwargs):
    if instance.is_deleted:
        type_changement = "DELETED"
    elif created:
        type_changement = "CREATED"
    else:
        type_changement = "UPDATED"
    enregistrer_changement(
        instance, type_changement, name=instance.name, parent=str(instance.parent_id or "")
    )


@receiver(post_save, sender=File)
def fichier_modifie(sender, instance, created, **kwargs):
    if instance.is_deleted:
        type_changement = "DELETED"
    elif created:
        type_changement = "CREATED"
    else:
        type_changement = "UPDATED"
    enregistrer_changement(
        instance,
        type_changement,
        name=instance.name,
        folder=str(instance.folder_id),
        version=(
            instance.current_version.version_number if instance.current_version_id else 0
        ),
        checksum=(
            instance.current_version.checksum_sha256 if instance.current_version_id else ""
        ),
        size=instance.size_bytes,
    )


@receiver(post_delete, sender=File)
def fichier_supprime(sender, instance, **kwargs):
    try:
        enregistrer_changement(instance, "DELETED", name=instance.name, purge=True)
    except Exception:  # pragma: no cover - suppression en cascade
        pass
