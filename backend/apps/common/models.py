import uuid

from django.db import models


class UUIDModel(models.Model):
    """Identifiant public UUID.

    Les identifiants sont des UUID v4 et non des entiers sequentiels : cela
    empeche l'enumeration des ressources et permet au client hors ligne de
    generer lui-meme l'identifiant d'un noeud cree sans reseau, sans avoir a
    le reecrire lors de la synchronisation.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    def vivants(self):
        return self.filter(is_deleted=False)

    def corbeille(self):
        return self.filter(is_deleted=True)


class SoftDeleteModel(models.Model):
    """Suppression logique : rien ne disparait avant la purge administrative."""

    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    objects = SoftDeleteQuerySet.as_manager()

    class Meta:
        abstract = True
