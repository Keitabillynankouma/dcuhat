from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.common.models import UUIDModel


class Action(models.TextChoices):
    LOGIN = "LOGIN", "Connexion"
    LOGIN_FAILED = "LOGIN_FAILED", "Echec de connexion"
    LOGOUT = "LOGOUT", "Deconnexion"
    FILE_UPLOAD = "FILE_UPLOAD", "Televersement"
    FILE_DOWNLOAD = "FILE_DOWNLOAD", "Telechargement"
    FILE_VIEW = "FILE_VIEW", "Consultation"
    FILE_RENAME = "FILE_RENAME", "Renommage de fichier"
    FILE_MOVE = "FILE_MOVE", "Deplacement de fichier"
    FILE_DELETE = "FILE_DELETE", "Suppression de fichier"
    FILE_RESTORE = "FILE_RESTORE", "Restauration de fichier"
    VERSION_RESTORE = "VERSION_RESTORE", "Restauration de version"
    FOLDER_CREATE = "FOLDER_CREATE", "Creation de dossier"
    FOLDER_RENAME = "FOLDER_RENAME", "Renommage de dossier"
    FOLDER_MOVE = "FOLDER_MOVE", "Deplacement de dossier"
    FOLDER_DELETE = "FOLDER_DELETE", "Suppression de dossier"
    FOLDER_RESTORE = "FOLDER_RESTORE", "Restauration de dossier"
    PERMISSION_GRANT = "PERMISSION_GRANT", "Attribution de droit"
    PERMISSION_REVOKE = "PERMISSION_REVOKE", "Retrait de droit"
    SHARE_LINK_CREATE = "SHARE_LINK_CREATE", "Creation de lien"
    SHARE_LINK_ACCESS = "SHARE_LINK_ACCESS", "Acces par lien"
    SYNC_CONFLICT = "SYNC_CONFLICT", "Conflit de synchronisation"
    USER_CREATE = "USER_CREATE", "Creation de compte"
    USER_DISABLE = "USER_DISABLE", "Desactivation de compte"
    ROLE_CHANGE = "ROLE_CHANGE", "Changement de role"
    TRASH_PURGE = "TRASH_PURGE", "Purge de la corbeille"
    GEO_CONVERT = "GEO_CONVERT", "Conversion geospatiale"


class ActivityLog(UUIDModel):
    """Journal en ecriture seule.

    Aucune API de modification ni de suppression n'est exposee sur cette table ;
    en production, le role SQL applicatif n'a que le droit INSERT et SELECT.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="activites",
    )
    actor_label = models.CharField(max_length=200, blank=True)
    action = models.CharField(max_length=30, choices=Action.choices, db_index=True)
    target_type = models.CharField(max_length=30, blank=True)
    target_id = models.CharField(max_length=64, blank=True, db_index=True)
    target_path = models.TextField(blank=True)
    service = models.ForeignKey(
        "accounts.Service", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="activites",
    )
    device = models.ForeignKey(
        "accounts.Device", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="activites",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "entree de journal"
        verbose_name_plural = "journal d'activite"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["actor", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.target_path}"
