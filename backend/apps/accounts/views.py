from __future__ import annotations

import base64
import io

import pyotp
from django.contrib.auth import authenticate
from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.services import journaliser
from apps.common.exceptions import OperationInvalide

from .models import Device, Role, Service, User
from .permissions import EstAdministrateur
from .serializers import (
    ChangePasswordSerializer,
    DeviceSerializer,
    LoginSerializer,
    ServiceSerializer,
    UserCreateSerializer,
    UserSerializer,
    genere_mot_de_passe,
)


def jetons(utilisateur) -> dict:
    refresh = RefreshToken.for_user(utilisateur)
    refresh["role"] = utilisateur.role
    refresh["service"] = str(utilisateur.service_id or "")
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


@extend_schema(request=LoginSerializer, responses=OpenApiTypes.OBJECT)
class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()
        utilisateur = User.objects.filter(email=email).first()

        if utilisateur and utilisateur.est_verrouille:
            journaliser("LOGIN_FAILED", acteur=utilisateur, motif="compte_verrouille")
            return Response(
                {
                    "code": "ACCOUNT_LOCKED",
                    "detail": "Compte temporairement verrouille apres plusieurs echecs.",
                },
                status=status.HTTP_423_LOCKED,
            )

        authentifie = authenticate(
            request, username=email, password=serializer.validated_data["password"]
        )
        if authentifie is None:
            if utilisateur:
                utilisateur.enregistrer_echec_connexion()
            journaliser("LOGIN_FAILED", acteur=utilisateur, email=email)
            return Response(
                {"code": "INVALID_CREDENTIALS", "detail": "Identifiants incorrects."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if authentifie.totp_enabled:
            code = serializer.validated_data.get("totp", "")
            if not code:
                return Response(
                    {"code": "TOTP_REQUIRED", "detail": "Code de verification requis."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            if not pyotp.TOTP(authentifie.totp_secret).verify(code, valid_window=1):
                authentifie.enregistrer_echec_connexion()
                journaliser("LOGIN_FAILED", acteur=authentifie, motif="totp_invalide")
                return Response(
                    {"code": "TOTP_INVALID", "detail": "Code de verification incorrect."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

        authentifie.enregistrer_succes_connexion()
        journaliser("LOGIN", acteur=authentifie)
        donnees = jetons(authentifie)
        donnees["utilisateur"] = UserSerializer(authentifie).data
        return Response(donnees)


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class LogoutView(APIView):
    def post(self, request):
        journaliser("LOGOUT", acteur=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(
            **{
                champ: getattr(request.user, champ)
                for champ in ("role", "service", "is_active")
            }
        )
        return Response(serializer.data)


@extend_schema(request=ChangePasswordSerializer, responses=OpenApiTypes.OBJECT)
class ChangePasswordView(APIView):
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        if not request.user.check_password(serializer.validated_data["ancien"]):
            raise OperationInvalide("Mot de passe actuel incorrect.")
        request.user.set_password(serializer.validated_data["nouveau"])
        request.user.must_change_password = False
        request.user.save(update_fields=["password", "must_change_password", "updated_at"])
        return Response({"detail": "Mot de passe modifie."})


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class TotpSetupView(APIView):
    def post(self, request):
        secret = pyotp.random_base32()
        request.user.totp_secret = secret
        request.user.save(update_fields=["totp_secret", "updated_at"])
        uri = pyotp.TOTP(secret).provisioning_uri(
            name=request.user.email, issuer_name="DCUHAT Lambayin"
        )
        image = ""
        try:
            import qrcode

            tampon = io.BytesIO()
            qrcode.make(uri).save(tampon, format="PNG")
            image = base64.b64encode(tampon.getvalue()).decode()
        except Exception:  # pragma: no cover
            pass
        return Response({"secret": secret, "uri": uri, "qrcode_png_base64": image})

    def put(self, request):
        code = request.data.get("code", "")
        if not pyotp.TOTP(request.user.totp_secret).verify(code, valid_window=1):
            raise OperationInvalide("Code incorrect.")
        request.user.totp_enabled = True
        request.user.save(update_fields=["totp_enabled", "updated_at"])
        return Response({"detail": "Double authentification activee."})

    def delete(self, request):
        request.user.totp_enabled = False
        request.user.totp_secret = ""
        request.user.save(update_fields=["totp_enabled", "totp_secret", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserViewSet(viewsets.ModelViewSet):
    """Gestion des comptes agents. Reservee aux administrateurs."""

    permission_classes = [IsAuthenticated, EstAdministrateur]
    filterset_fields = ["role", "service", "is_active"]

    def get_queryset(self):
        requete = User.objects.select_related("service").all()
        params = self.request.query_params
        if params.get("q"):
            recherche = params["q"]
            requete = requete.filter(
                Q(email__icontains=recherche)
                | Q(first_name__icontains=recherche)
                | Q(last_name__icontains=recherche)
                | Q(matricule__icontains=recherche)
            )
        if params.get("role"):
            requete = requete.filter(role=params["role"])
        if params.get("service"):
            requete = requete.filter(service_id=params["service"])
        if params.get("actifs") == "1":
            requete = requete.filter(is_active=True)
        return requete

    def get_serializer_class(self):
        return UserCreateSerializer if self.action == "create" else UserSerializer

    def perform_create(self, serializer):
        utilisateur = serializer.save()
        journaliser("USER_CREATE", cible=utilisateur, target_type="USER",
                    role=utilisateur.role)

    def perform_update(self, serializer):
        ancien_role = serializer.instance.role
        utilisateur = serializer.save()
        if utilisateur.role != ancien_role:
            journaliser(
                "ROLE_CHANGE", cible=utilisateur, target_type="USER",
                ancien=ancien_role, nouveau=utilisateur.role,
            )

    def perform_destroy(self, instance):
        """Un compte n'est jamais supprime : il est desactive.

        Le journal d'activite attribue chaque action a un agent nomme ;
        supprimer le compte rendrait l'historique illisible."""
        if instance.id == self.request.user.id:
            raise OperationInvalide("Vous ne pouvez pas desactiver votre propre compte.")
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        journaliser("USER_DISABLE", cible=instance, target_type="USER")

    @action(detail=True, methods=["post"])
    def role(self, request, pk=None):
        utilisateur = self.get_object()
        nouveau = request.data.get("role")
        if nouveau not in dict(Role.choices):
            raise OperationInvalide("Role inconnu.")
        if utilisateur.id == request.user.id and nouveau != Role.ADMIN:
            raise OperationInvalide(
                "Vous ne pouvez pas retirer votre propre role d'administrateur."
            )
        ancien = utilisateur.role
        utilisateur.role = nouveau
        utilisateur.save(update_fields=["role", "updated_at"])
        journaliser(
            "ROLE_CHANGE", cible=utilisateur, target_type="USER",
            ancien=ancien, nouveau=utilisateur.role,
        )
        return Response(UserSerializer(utilisateur).data)

    @action(detail=True, methods=["post"])
    def activer(self, request, pk=None):
        utilisateur = self.get_object()
        utilisateur.is_active = True
        utilisateur.failed_login_attempts = 0
        utilisateur.locked_until = None
        utilisateur.save(
            update_fields=["is_active", "failed_login_attempts", "locked_until", "updated_at"]
        )
        return Response(UserSerializer(utilisateur).data)

    @action(detail=True, methods=["post"], url_path="reinitialiser-mot-de-passe")
    def reinitialiser_mot_de_passe(self, request, pk=None):
        """Genere un mot de passe provisoire, affiche une seule fois."""
        utilisateur = self.get_object()
        mot_de_passe = request.data.get("mot_de_passe") or genere_mot_de_passe()
        utilisateur.set_password(mot_de_passe)
        utilisateur.must_change_password = True
        utilisateur.failed_login_attempts = 0
        utilisateur.locked_until = None
        utilisateur.save(
            update_fields=[
                "password", "must_change_password", "failed_login_attempts",
                "locked_until", "updated_at",
            ]
        )
        journaliser("USER_CREATE", cible=utilisateur, target_type="USER",
                    action_detail="reinitialisation_mot_de_passe")
        return Response(
            {
                "utilisateur": UserSerializer(utilisateur).data,
                "mot_de_passe_provisoire": mot_de_passe,
                "avertissement": (
                    "Ce mot de passe n'est affiche qu'une seule fois. "
                    "Transmettez-le a l'agent, qui devra le changer a sa "
                    "premiere connexion."
                ),
            }
        )


class StatistiquesView(APIView):
    """Chiffres de tete de la plateforme, pour le tableau de bord."""

    permission_classes = [IsAuthenticated, EstAdministrateur]

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        from django.db.models import Count, Sum

        from apps.audit.models import ActivityLog
        from apps.geo.models import GeoAsset
        from apps.storage.models import File, FileVersion, Folder

        depuis = timezone.now() - timezone.timedelta(days=7)
        octets = (
            FileVersion.objects.aggregate(total=Sum("size_bytes"))["total"] or 0
        )
        return Response(
            {
                "agents": {
                    "total": User.objects.count(),
                    "actifs": User.objects.filter(is_active=True).count(),
                    "par_role": list(
                        User.objects.values("role").annotate(nombre=Count("id")).order_by("role")
                    ),
                },
                "services": Service.objects.filter(is_active=True).count(),
                "dossiers": Folder.objects.filter(is_deleted=False).count(),
                "fichiers": {
                    "total": File.objects.filter(is_deleted=False).count(),
                    "geospatiaux": GeoAsset.objects.filter(file__is_deleted=False).count(),
                    "corbeille": File.objects.filter(is_deleted=True).count(),
                    "par_type": list(
                        File.objects.filter(is_deleted=False)
                        .values("kind")
                        .annotate(nombre=Count("id"))
                        .order_by("-nombre")
                    ),
                },
                "stockage_octets": octets,
                "activite_7_jours": ActivityLog.objects.filter(created_at__gte=depuis).count(),
                "conflits_ouverts": _conflits_ouverts(),
            }
        )


def _conflits_ouverts() -> int:
    from apps.sync.models import StatutOperation, SyncOperation

    return SyncOperation.objects.filter(status=StatutOperation.CONFLICT).count()


class ServiceViewSet(viewsets.ModelViewSet):
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        return [IsAuthenticated(), EstAdministrateur()]


class DeviceViewSet(viewsets.ModelViewSet):
    serializer_class = DeviceSerializer

    def get_queryset(self):
        return Device.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_destroy(self, instance):
        instance.is_revoked = True
        instance.save(update_fields=["is_revoked", "updated_at"])
