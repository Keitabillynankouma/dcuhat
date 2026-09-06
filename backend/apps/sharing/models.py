from __future__ import annotations

import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import TimeStampedModel, UUIDModel


class Niveau(models.TextChoices):
    READ = "READ", "Consulter"
    COMMENT = "COMMENT", "Commenter"
    WRITE = "WRITE", "Modifier"
    MANAGE = "MANAGE", "Gerer"


#: Hierarchie des niveaux : MANAGE contient WRITE contient COMMENT contient READ.
POIDS_NIVEAU = {Niveau.READ: 1, Niveau.COMMENT: 2, Niveau.WRITE: 3, Niveau.MANAGE: 4}


def au_moins(niveau: str, requis: str) -> bool:
    return POIDS_NIVEAU.get(niveau, 0) >= POIDS_NIVEAU.get(requis, 0)


class Permission(UUIDModel, TimeStampedModel):
    """Droit explicite accorde a un agent ou a un service sur un noeud."""

    folder = models.ForeignKey(
        "storage.Folder", null=True, blank=True, on_delete=models.CASCADE,
        related_name="permissions",
    )
    file = models.ForeignKey(
        "storage.File", null=True, blank=True, on_delete=models.CASCADE,
        related_name="permissions",
    )
    grantee_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE,
        related_name="permissions_recues",
    )
    grantee_service = models.ForeignKey(
        "accounts.Service", null=True, blank=True, on_delete=models.CASCADE,
        related_name="permissions_recues",
    )
    level = models.CharField(max_length=10, choices=Niveau.choices, default=Niveau.READ)
    inherit = models.BooleanField(
        default=True, help_text="S'applique a tout le sous-arbre du dossier."
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "permission"
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(folder__isnull=False, file__isnull=True)
                    | models.Q(folder__isnull=True, file__isnull=False)
                ),
                name="permission_cible_unique",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(grantee_user__isnull=False, grantee_service__isnull=True)
                    | models.Q(grantee_user__isnull=True, grantee_service__isnull=False)
                ),
                name="permission_beneficiaire_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["grantee_user", "folder"]),
            models.Index(fields=["grantee_service", "folder"]),
        ]

    @property
    def active(self) -> bool:
        return not self.expires_at or self.expires_at > timezone.now()


class ShareLink(UUIDModel, TimeStampedModel):
    """Lien de partage pour un destinataire externe (invite)."""

    token = models.CharField(max_length=64, unique=True, editable=False)
    folder = models.ForeignKey(
        "storage.Folder", null=True, blank=True, on_delete=models.CASCADE,
        related_name="liens",
    )
    file = models.ForeignKey(
        "storage.File", null=True, blank=True, on_delete=models.CASCADE,
        related_name="liens",
    )
    level = models.CharField(max_length=10, choices=Niveau.choices, default=Niveau.READ)
    password_hash = models.CharField(max_length=255, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    max_downloads = models.PositiveIntegerField(null=True, blank=True)
    download_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="liens_crees"
    )
    is_revoked = models.BooleanField(default=False)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "lien de partage"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(folder__isnull=False, file__isnull=True)
                    | models.Q(folder__isnull=True, file__isnull=False)
                ),
                name="lien_cible_unique",
            )
        ]

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)[:64]
        super().save(*args, **kwargs)

    @property
    def valide(self) -> bool:
        if self.is_revoked:
            return False
        if self.expires_at and self.expires_at <= timezone.now():
            return False
        if self.max_downloads and self.download_count >= self.max_downloads:
            return False
        return True
