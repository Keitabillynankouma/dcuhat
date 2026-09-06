from __future__ import annotations

from rest_framework import serializers

from apps.accounts.models import Service
from apps.sharing.services import niveau_sur_dossier, niveau_sur_fichier

from .models import (
    CHAMPS_METIER,
    Comment,
    File,
    FileMetadata,
    FileVersion,
    Folder,
    Tag,
)


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name", "color", "service"]


class FolderSerializer(serializers.ModelSerializer):
    # Declare explicitement : la contrainte d'unicite (parent, name) pousse
    # sinon DRF a rendre `parent` obligatoire, ce qui interdirait la creation
    # d'un espace racine.
    parent = serializers.PrimaryKeyRelatedField(
        queryset=Folder.objects.all(), required=False, allow_null=True
    )
    service = serializers.PrimaryKeyRelatedField(
        queryset=Service.objects.all(), required=False, allow_null=True
    )
    owner_nom = serializers.CharField(source="owner.nom_complet", read_only=True)
    service_nom = serializers.CharField(source="service.name", read_only=True)
    niveau = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()

    class Meta:
        model = Folder
        fields = [
            "id", "name", "parent", "path", "depth", "owner", "owner_nom",
            "service", "service_nom", "description", "color", "icon",
            "size_bytes", "file_count", "is_deleted", "deleted_at",
            "created_at", "updated_at", "niveau", "type",
        ]
        read_only_fields = [
            "id", "path", "depth", "owner", "size_bytes", "file_count",
            "is_deleted", "deleted_at", "created_at", "updated_at",
        ]
        # La contrainte d'unicite (parent, name) est verifiee dans la couche
        # metier, qui sait renvoyer un NAME_CONFLICT explicite ou suffixer le
        # nom lors d'une synchronisation. Le validateur automatique de DRF
        # rendrait de surcroit `parent` obligatoire, empechant la creation
        # d'un espace racine.
        validators: list = []

    def get_type(self, obj):
        return "dossier"

    def get_niveau(self, obj):
        utilisateur = self.context.get("request").user if self.context.get("request") else None
        return niveau_sur_dossier(utilisateur, obj)


class FileVersionSerializer(serializers.ModelSerializer):
    auteur = serializers.CharField(source="uploaded_by.nom_complet", read_only=True)

    class Meta:
        model = FileVersion
        fields = [
            "id", "version_number", "size_bytes", "checksum_sha256", "mime_type",
            "uploaded_by", "auteur", "comment", "origin", "is_conflict_copy",
            "created_at",
        ]


class FileMetadataSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileMetadata
        fields = ["id", "key", "value", "value_type", "source"]


class FileSerializer(serializers.ModelSerializer):
    owner_nom = serializers.CharField(source="owner.nom_complet", read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    version_courante = serializers.IntegerField(
        source="current_version.version_number", read_only=True, default=0
    )
    chemin = serializers.CharField(source="chemin_complet", read_only=True)
    est_geospatial = serializers.BooleanField(read_only=True)
    niveau = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()

    class Meta:
        model = File
        fields = [
            "id", "name", "folder", "chemin", "owner", "owner_nom", "service",
            "mime_type", "kind", "size_bytes", "description", "tags",
            "version_courante", "est_geospatial", "is_locked", "locked_by",
            "is_deleted", "deleted_at", "created_at", "updated_at",
            "niveau", "type",
        ]
        read_only_fields = [
            "id", "folder", "owner", "service", "mime_type", "kind", "size_bytes",
            "is_locked", "locked_by", "is_deleted", "deleted_at",
            "created_at", "updated_at",
        ]

    def get_type(self, obj):
        return "fichier"

    def get_niveau(self, obj):
        utilisateur = self.context.get("request").user if self.context.get("request") else None
        return niveau_sur_fichier(utilisateur, obj)


class FileDetailSerializer(FileSerializer):
    metadata = FileMetadataSerializer(many=True, read_only=True)
    versions = FileVersionSerializer(many=True, read_only=True)
    champs_metier = serializers.SerializerMethodField()

    class Meta(FileSerializer.Meta):
        fields = FileSerializer.Meta.fields + ["metadata", "versions", "champs_metier"]

    def get_champs_metier(self, obj):
        return [{"cle": cle, "libelle": libelle} for cle, libelle in CHAMPS_METIER]


class CommentSerializer(serializers.ModelSerializer):
    auteur_nom = serializers.CharField(source="author.nom_complet", read_only=True)

    class Meta:
        model = Comment
        fields = ["id", "file", "author", "auteur_nom", "body", "parent", "created_at"]
        read_only_fields = ["id", "file", "author", "created_at"]


class UploadInitSerializer(serializers.Serializer):
    nom = serializers.CharField(max_length=255)
    dossier = serializers.UUIDField()
    taille = serializers.IntegerField(min_value=1)
    checksum_sha256 = serializers.CharField(required=False, allow_blank=True)
    commentaire = serializers.CharField(required=False, allow_blank=True, max_length=500)
    client_id = serializers.UUIDField(required=False, allow_null=True)
