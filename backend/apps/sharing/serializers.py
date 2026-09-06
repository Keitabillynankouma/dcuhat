from rest_framework import serializers

from .models import Permission, ShareLink


class PermissionSerializer(serializers.ModelSerializer):
    beneficiaire = serializers.SerializerMethodField()
    cible = serializers.SerializerMethodField()

    class Meta:
        model = Permission
        fields = [
            "id", "folder", "file", "grantee_user", "grantee_service", "level",
            "inherit", "expires_at", "granted_by", "beneficiaire", "cible",
            "created_at",
        ]
        read_only_fields = ["id", "granted_by", "created_at"]

    def get_beneficiaire(self, obj):
        if obj.grantee_user_id:
            return {"type": "agent", "nom": str(obj.grantee_user)}
        return {"type": "service", "nom": str(obj.grantee_service)}

    def get_cible(self, obj):
        if obj.folder_id:
            return {"type": "dossier", "nom": obj.folder.name, "chemin": obj.folder.path}
        return {"type": "fichier", "nom": obj.file.name}

    def validate(self, donnees):
        if bool(donnees.get("folder")) == bool(donnees.get("file")):
            raise serializers.ValidationError(
                "Indiquez exactement un dossier ou un fichier."
            )
        if bool(donnees.get("grantee_user")) == bool(donnees.get("grantee_service")):
            raise serializers.ValidationError(
                "Indiquez exactement un agent ou un service beneficiaire."
            )
        return donnees


class ShareLinkSerializer(serializers.ModelSerializer):
    mot_de_passe = serializers.CharField(write_only=True, required=False, allow_blank=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = ShareLink
        fields = [
            "id", "token", "url", "folder", "file", "level", "expires_at",
            "max_downloads", "download_count", "is_revoked", "note",
            "mot_de_passe", "created_at",
        ]
        read_only_fields = ["id", "token", "download_count", "created_at"]

    def get_url(self, obj):
        requete = self.context.get("request")
        chemin = f"/partage/{obj.token}"
        return requete.build_absolute_uri(chemin) if requete else chemin

    def create(self, validated_data):
        from django.contrib.auth.hashers import make_password

        mot_de_passe = validated_data.pop("mot_de_passe", "")
        lien = ShareLink(**validated_data)
        if mot_de_passe:
            lien.password_hash = make_password(mot_de_passe)
        lien.save()
        return lien
