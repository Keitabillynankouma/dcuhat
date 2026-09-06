"""Recherche unifiee : plein texte, filtres metier et emprise geographique
dans une seule requete."""

from __future__ import annotations

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import F, Q
from rest_framework.response import Response
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView

from apps.geo.models import GeoAsset
from apps.geo.views import bbox_depuis_parametre
from apps.sharing.services import dossiers_visibles, fichiers_visibles
from apps.storage.serializers import FileSerializer, FolderSerializer


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class SearchView(APIView):
    def get(self, request):
        params = request.query_params
        texte = (params.get("q") or "").strip()

        fichiers = fichiers_visibles(request.user).select_related(
            "owner", "folder", "current_version"
        )
        dossiers = dossiers_visibles(request.user)

        if texte:
            requete_texte = SearchQuery(texte, config="french", search_type="websearch")
            fichiers = (
                fichiers.filter(
                    Q(search_vector=requete_texte)
                    | Q(name__icontains=texte)
                    | Q(description__icontains=texte)
                    | Q(tags__name__icontains=texte)
                    | Q(metadata__value__icontains=texte)
                )
                .annotate(pertinence=SearchRank(F("search_vector"), requete_texte))
                .order_by("-pertinence", "-updated_at")
                .distinct()
            )
            dossiers = dossiers.filter(name__icontains=texte)

        if params.get("kind"):
            fichiers = fichiers.filter(kind=params["kind"].upper())
        if params.get("service"):
            fichiers = fichiers.filter(service_id=params["service"])
        if params.get("tag"):
            fichiers = fichiers.filter(tags__name=params["tag"])
        if params.get("date_from"):
            fichiers = fichiers.filter(created_at__gte=params["date_from"])
        if params.get("date_to"):
            fichiers = fichiers.filter(created_at__lte=params["date_to"])
        if params.get("proprietaire"):
            fichiers = fichiers.filter(owner_id=params["proprietaire"])
        for cle, valeur in params.items():
            if cle.startswith("meta_"):
                fichiers = fichiers.filter(
                    metadata__key=cle[5:], metadata__value__icontains=valeur
                )
        if params.get("bbox"):
            emprise = bbox_depuis_parametre(params["bbox"])
            ids = GeoAsset.objects.filter(extent__intersects=emprise).values_list(
                "file_id", flat=True
            )
            fichiers = fichiers.filter(pk__in=ids)

        limite = min(int(params.get("limite", 100)), 500)
        return Response(
            {
                "requete": texte,
                "total_fichiers": fichiers.count(),
                "total_dossiers": dossiers.count(),
                "fichiers": FileSerializer(
                    fichiers[:limite], many=True, context={"request": request}
                ).data,
                "dossiers": FolderSerializer(
                    dossiers[:50], many=True, context={"request": request}
                ).data,
            }
        )


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class SuggestView(APIView):
    def get(self, request):
        texte = (request.query_params.get("q") or "").strip()
        if len(texte) < 2:
            return Response([])
        noms = (
            fichiers_visibles(request.user)
            .filter(name__icontains=texte)
            .values_list("name", flat=True)[:10]
        )
        dossiers = (
            dossiers_visibles(request.user)
            .filter(name__icontains=texte)
            .values_list("name", flat=True)[:5]
        )
        return Response(
            [{"valeur": n, "type": "fichier"} for n in noms]
            + [{"valeur": d, "type": "dossier"} for d in dossiers]
        )
