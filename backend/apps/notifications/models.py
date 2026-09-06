from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import TimeStampedModel, UUIDModel


class TypeNotification(models.TextChoices):
    PARTAGE_RECU = "PARTAGE_RECU", "Un element vous a ete partage"
    NOUVEAU_FICHIER = "NOUVEAU_FICHIER", "Nouveau fichier dans un dossier suivi"
    NOUVELLE_VERSION = "NOUVELLE_VERSION", "Nouvelle version d'un fichier"
    COMMENTAIRE = "COMMENTAIRE", "Nouveau commentaire"
    CONFLIT_SYNC = "CONFLIT_SYNC", "Conflit de synchronisation"
    CONVERSION_TERMINEE = "CONVERSION_TERMINEE", "Conversion terminee"
    QUOTA_PROCHE = "QUOTA_PROCHE", "Quota bientot atteint"


class Notification(UUIDModel, TimeStampedModel):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    type = models.CharField(max_length=25, choices=TypeNotification.choices)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    target_type = models.CharField(max_length=20, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "notification"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "is_read", "-created_at"])]

    def marquer_lue(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at", "updated_at"])


class NotificationPreference(UUIDModel, TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="preferences_notif"
    )
    type = models.CharField(max_length=25, choices=TypeNotification.choices)
    in_app = models.BooleanField(default=True)
    email = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "type"], name="preference_unique")
        ]
