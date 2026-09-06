from __future__ import annotations

import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.common.models import TimeStampedModel, UUIDModel


class Role(models.TextChoices):
    ADMIN = "ADMIN", "Administrateur"
    DIRECTEUR = "DIRECTEUR", "Directeur"
    CHEF_SERVICE = "CHEF_SERVICE", "Chef de service"
    AGENT = "AGENT", "Agent"
    LECTEUR = "LECTEUR", "Lecteur"
    INVITE = "INVITE", "Invite"


#: Hierarchie des roles, du plus faible au plus fort. Sert aux comparaisons.
POIDS_ROLE = {
    Role.INVITE: 0,
    Role.LECTEUR: 1,
    Role.AGENT: 2,
    Role.CHEF_SERVICE: 3,
    Role.DIRECTEUR: 4,
    Role.ADMIN: 5,
}


class Service(UUIDModel, TimeStampedModel):
    """Service de la Direction (Urbanisme, Cadastre, Habitat...)."""

    name = models.CharField("nom", max_length=150, unique=True)
    code = models.CharField(max_length=30, unique=True)
    description = models.TextField(blank=True)
    quota_bytes = models.BigIntegerField(default=0)  # 0 = quota par defaut
    root_folder = models.ForeignKey(
        "storage.Folder", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="service_racine",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "service"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def quota_effectif(self) -> int:
        from django.conf import settings

        if self.quota_bytes:
            return self.quota_bytes
        return settings.DEFAULT_SERVICE_QUOTA_GB * 1024**3


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("L'adresse e-mail est obligatoire.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("role", Role.ADMIN)
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("must_change_password", False)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField("adresse e-mail", unique=True)
    matricule = models.CharField(max_length=32, blank=True, null=True, unique=True)
    first_name = models.CharField("prenom", max_length=100, blank=True)
    last_name = models.CharField("nom", max_length=100, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.AGENT)
    service = models.ForeignKey(
        Service, null=True, blank=True, on_delete=models.SET_NULL, related_name="agents"
    )
    fonction = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    must_change_password = models.BooleanField(default=True)

    totp_secret = models.CharField(max_length=64, blank=True)
    totp_enabled = models.BooleanField(default=False)

    storage_quota_bytes = models.BigIntegerField(default=0)
    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "utilisateur"
        ordering = ["last_name", "first_name"]
        indexes = [models.Index(fields=["role"]), models.Index(fields=["service"])]

    def __str__(self):
        return self.nom_complet or self.email

    def save(self, *args, **kwargs):
        # Le role ADMIN donne acces a l'administration Django : sans cela, un
        # agent promu administrateur par l'API se retrouverait avec tous les
        # droits metier mais une porte fermee sur /admin/. Le role ADMIN vaut
        # deja MANAGE sur tout dans le moteur de permissions : lui refuser
        # l'administration serait incoherent, pas plus sur.
        if self.role == Role.ADMIN and not (self.is_staff and self.is_superuser):
            self.is_staff = True
            self.is_superuser = True
            champs = kwargs.get("update_fields")
            if champs is not None:
                kwargs["update_fields"] = set(champs) | {"is_staff", "is_superuser"}
        super().save(*args, **kwargs)

    @property
    def nom_complet(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def est_admin(self) -> bool:
        return self.role == Role.ADMIN or self.is_superuser

    @property
    def est_directeur(self) -> bool:
        return self.role == Role.DIRECTEUR

    @property
    def est_chef_service(self) -> bool:
        return self.role == Role.CHEF_SERVICE

    @property
    def poids_role(self) -> int:
        return POIDS_ROLE.get(self.role, 0)

    @property
    def est_verrouille(self) -> bool:
        return bool(self.locked_until and self.locked_until > timezone.now())

    def enregistrer_echec_connexion(self):
        from django.conf import settings

        self.failed_login_attempts += 1
        if self.failed_login_attempts >= settings.LOGIN_MAX_FAILED_ATTEMPTS:
            self.locked_until = timezone.now() + timezone.timedelta(
                minutes=settings.LOGIN_LOCKOUT_MINUTES
            )
        self.save(update_fields=["failed_login_attempts", "locked_until", "updated_at"])

    def enregistrer_succes_connexion(self):
        self.failed_login_attempts = 0
        self.locked_until = None
        self.last_seen_at = timezone.now()
        self.save(
            update_fields=[
                "failed_login_attempts",
                "locked_until",
                "last_seen_at",
                "updated_at",
            ]
        )


class Device(UUIDModel, TimeStampedModel):
    """Appareil enregistre pour la synchronisation hors ligne."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="devices")
    label = models.CharField(max_length=100)
    platform = models.CharField(max_length=50, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    sync_cursor = models.BigIntegerField(default=0)
    is_revoked = models.BooleanField(default=False)

    class Meta:
        verbose_name = "appareil"
        ordering = ["-last_sync_at"]

    def __str__(self):
        return f"{self.label} ({self.user.email})"
