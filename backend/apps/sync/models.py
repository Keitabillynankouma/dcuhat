from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel, UUIDModel


class TypeOperation(models.TextChoices):
    CREATE_FOLDER = "CREATE_FOLDER", "Creation de dossier"
    RENAME = "RENAME", "Renommage"
    MOVE = "MOVE", "Deplacement"
    UPLOAD_VERSION = "UPLOAD_VERSION", "Nouvelle version"
    DELETE = "DELETE", "Suppression"
    RESTORE = "RESTORE", "Restauration"
    SET_METADATA = "SET_METADATA", "Metadonnees"


class StatutOperation(models.TextChoices):
    PENDING = "PENDING", "En attente"
    APPLIED = "APPLIED", "Appliquee"
    CONFLICT = "CONFLICT", "En conflit"
    REJECTED = "REJECTED", "Rejetee"


class Resolution(models.TextChoices):
    SERVER_WINS = "SERVER_WINS", "Version serveur conservee"
    CLIENT_WINS = "CLIENT_WINS", "Version hors ligne conservee"
    BOTH_KEPT = "BOTH_KEPT", "Les deux versions conservees"
    MANUAL = "MANUAL", "A arbitrer"


class SyncOperation(TimeStampedModel):
    """Operation produite hors ligne et rejouee au retour du reseau.

    L'identifiant est genere par le client : rejouer deux fois le meme lot est
    sans effet, ce qui rend la synchronisation sure sur une liaison qui coupe
    au milieu d'un envoi.
    """

    id = models.UUIDField(primary_key=True, editable=False)
    device = models.ForeignKey(
        "accounts.Device", on_delete=models.CASCADE, related_name="operations"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="operations_sync"
    )
    op_type = models.CharField(max_length=20, choices=TypeOperation.choices)
    target_type = models.CharField(max_length=20)  # FOLDER | FILE
    target_id = models.UUIDField()
    payload = models.JSONField(default=dict, blank=True)
    client_seq = models.BigIntegerField()
    base_version = models.IntegerField(null=True, blank=True)
    client_timestamp = models.DateTimeField()
    status = models.CharField(
        max_length=10, choices=StatutOperation.choices, default=StatutOperation.PENDING
    )
    conflict_resolution = models.CharField(
        max_length=15, choices=Resolution.choices, blank=True
    )
    applied_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    result = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "operation de synchronisation"
        ordering = ["device", "client_seq"]
        indexes = [
            models.Index(fields=["device", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]


class ChangeType(models.TextChoices):
    CREATED = "CREATED", "Cree"
    UPDATED = "UPDATED", "Modifie"
    MOVED = "MOVED", "Deplace"
    DELETED = "DELETED", "Supprime"
    RESTORED = "RESTORED", "Restaure"
    PERMISSION = "PERMISSION", "Droits modifies"


class ChangeLog(models.Model):
    """Journal ordonne des changements servant le delta descendant.

    Le client conserve le dernier `seq` recu ; le delta est simplement
    `seq > curseur`. Pas d'horloge a synchroniser, pas de fenetre a recouvrir.
    """

    seq = models.BigAutoField(primary_key=True)
    entity_type = models.CharField(max_length=20)  # FOLDER | FILE | PERMISSION
    entity_id = models.UUIDField(db_index=True)
    change_type = models.CharField(max_length=15, choices=ChangeType.choices)
    service = models.ForeignKey(
        "accounts.Service", null=True, blank=True, on_delete=models.CASCADE,
        related_name="changements",
    )
    folder_path = models.TextField(db_index=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "changement"
        ordering = ["seq"]
        indexes = [models.Index(fields=["service", "seq"])]
