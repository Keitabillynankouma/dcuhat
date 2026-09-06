from __future__ import annotations

from django.contrib.auth.password_validation import validate_password
from django.utils.crypto import get_random_string
from rest_framework import serializers

from .models import Device, Role, Service, User


def genere_mot_de_passe(longueur: int = 14) -> str:
    """Mot de passe provisoire lisible : ni ambigu a dicter, ni trivial."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    return get_random_string(longueur, alphabet)


class ServiceSerializer(serializers.ModelSerializer):
    quota_effectif = serializers.IntegerField(read_only=True)
    usage_octets = serializers.SerializerMethodField()
    nombre_agents = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = [
            "id", "name", "code", "description", "quota_bytes", "quota_effectif",
            "usage_octets", "nombre_agents", "root_folder", "is_active",
        ]
        read_only_fields = ["id", "root_folder"]

    def get_usage_octets(self, obj) -> int:
        from apps.storage.services import usage_service

        return usage_service(obj)

    def get_nombre_agents(self, obj) -> int:
        return obj.agents.filter(is_active=True).count()


class UserSerializer(serializers.ModelSerializer):
    nom_complet = serializers.CharField(read_only=True)
    service_nom = serializers.CharField(source="service.name", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "matricule", "first_name", "last_name", "nom_complet",
            "role", "service", "service_nom", "fonction", "phone", "is_active",
            "totp_enabled", "must_change_password", "last_seen_at", "created_at",
        ]
        read_only_fields = ["id", "totp_enabled", "last_seen_at", "created_at"]


class UserCreateSerializer(serializers.ModelSerializer):
    """Creation d'un agent par l'administrateur.

    Si aucun mot de passe n'est fourni, un mot de passe provisoire est genere
    et renvoye **une seule fois** dans la reponse : c'est ce que
    l'administrateur transmettra a l'agent, qui devra le changer a sa premiere
    connexion.
    """

    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    mot_de_passe_provisoire = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "matricule", "first_name", "last_name", "role",
            "service", "fonction", "phone", "password", "mot_de_passe_provisoire",
        ]

    def get_mot_de_passe_provisoire(self, obj) -> str:
        return getattr(obj, "_mot_de_passe_provisoire", "")

    def validate_email(self, valeur):
        valeur = valeur.lower().strip()
        if User.objects.filter(email=valeur).exists():
            raise serializers.ValidationError("Un compte existe deja pour cette adresse.")
        return valeur

    def validate_password(self, valeur):
        if valeur:
            validate_password(valeur)
        return valeur

    def create(self, validated_data):
        fourni = validated_data.pop("password", "")
        mot_de_passe = fourni or genere_mot_de_passe()
        utilisateur = User.objects.create_user(password=mot_de_passe, **validated_data)
        utilisateur._mot_de_passe_provisoire = "" if fourni else mot_de_passe
        return utilisateur


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    totp = serializers.CharField(required=False, allow_blank=True)


class ChangePasswordSerializer(serializers.Serializer):
    ancien = serializers.CharField(write_only=True)
    nouveau = serializers.CharField(write_only=True)

    def validate_nouveau(self, valeur):
        validate_password(valeur, self.context["request"].user)
        return valeur


class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = [
            "id", "label", "platform", "last_sync_at", "sync_cursor",
            "is_revoked", "created_at",
        ]
        read_only_fields = ["id", "last_sync_at", "sync_cursor", "created_at"]
