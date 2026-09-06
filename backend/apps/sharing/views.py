from __future__ import annotations

from django.contrib.auth.hashers import check_password
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView

from apps.audit.services import journaliser
from apps.common.exceptions import LienExpire, OperationInvalide
from apps.notifications.services import notifier
from apps.storage.models import File, Folder
from apps.storage.serializers import FileSerializer, FolderSerializer

from .models import Niveau, Permission, ShareLink
from .serializers import PermissionSerializer, ShareLinkSerializer
from .services import exiger


class PermissionViewSet(viewsets.ModelViewSet):
    serializer_class = PermissionSerializer

    def get_queryset(self):
        requete = Permission.objects.select_related(
            "folder", "file", "grantee_user", "grantee_service"
        )
        params = self.request.query_params
        if params.get("folder"):
            requete = requete.filter(folder_id=params["folder"])
        elif params.get("file"):
            requete = requete.filter(file_id=params["file"])
        elif not self.request.user.est_admin:
            requete = requete.filter(granted_by=self.request.user)
        return requete

    def perform_create(self, serializer):
        cible = serializer.validated_data.get("folder") or serializer.validated_data.get("file")
        exiger(self.request.user, cible, Niveau.MANAGE)
        permission = serializer.save(granted_by=self.request.user)
        journaliser(
            "PERMISSION_GRANT", acteur=self.request.user, cible=cible,
            niveau=permission.level, beneficiaire=str(
                permission.grantee_user or permission.grantee_service
            ),
        )
        if permission.grantee_user_id:
            notifier(
                permission.grantee_user,
                "PARTAGE_RECU",
                titre=f"« {getattr(cible, 'name', '')} » vous a ete partage",
                corps=f"Niveau d'acces : {permission.get_level_display()}.",
                cible=cible,
            )

    def perform_destroy(self, instance):
        cible = instance.folder or instance.file
        exiger(self.request.user, cible, Niveau.MANAGE)
        journaliser("PERMISSION_REVOKE", acteur=self.request.user, cible=cible)
        instance.delete()


class ShareLinkViewSet(viewsets.ModelViewSet):
    serializer_class = ShareLinkSerializer

    def get_queryset(self):
        if self.request.user.est_admin:
            return ShareLink.objects.all()
        return ShareLink.objects.filter(created_by=self.request.user)

    def perform_create(self, serializer):
        cible = serializer.validated_data.get("folder") or serializer.validated_data.get("file")
        if cible is None:
            raise OperationInvalide("Indiquez un dossier ou un fichier a partager.")
        exiger(self.request.user, cible, Niveau.MANAGE)
        lien = serializer.save(created_by=self.request.user)
        journaliser("SHARE_LINK_CREATE", acteur=self.request.user, cible=cible,
                    expire_le=str(lien.expires_at or ""))

    def perform_destroy(self, instance):
        instance.is_revoked = True
        instance.save(update_fields=["is_revoked", "updated_at"])


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class AccesLienView(APIView):
    """Acces invite par lien public."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, token):
        lien = get_object_or_404(ShareLink, token=token)
        if not lien.valide:
            raise LienExpire()
        if lien.password_hash:
            if not check_password(request.data.get("mot_de_passe", ""), lien.password_hash):
                raise OperationInvalide("Mot de passe incorrect.")

        journaliser(
            "SHARE_LINK_ACCESS",
            cible=lien.folder or lien.file,
            target_type="SHARE_LINK",
            token=token[:8],
        )
        if lien.file_id:
            return Response(
                {
                    "type": "fichier",
                    "fichier": FileSerializer(lien.file, context={"request": request}).data,
                    "niveau": lien.level,
                }
            )
        sous_dossiers = Folder.objects.filter(parent=lien.folder, is_deleted=False)
        fichiers = File.objects.filter(folder=lien.folder, is_deleted=False)
        return Response(
            {
                "type": "dossier",
                "dossier": FolderSerializer(lien.folder, context={"request": request}).data,
                "dossiers": FolderSerializer(
                    sous_dossiers, many=True, context={"request": request}
                ).data,
                "fichiers": FileSerializer(
                    fichiers, many=True, context={"request": request}
                ).data,
                "niveau": lien.level,
            }
        )
