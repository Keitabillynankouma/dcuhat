from __future__ import annotations

import json

from django.contrib.gis.geos import Point, Polygon
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView

from apps.audit.services import journaliser
from apps.common.exceptions import OperationInvalide
from apps.sharing.models import Niveau
from apps.sharing.services import exiger, fichiers_visibles
from apps.storage.models import File

from .models import ConversionJob, GeoAsset, GeoLayer
from .serializers import ConversionSerializer, GeoAssetSerializer, GeoLayerSerializer
from .tasks import analyser_fichier, convertir


def bbox_depuis_parametre(valeur: str) -> Polygon:
    try:
        min_x, min_y, max_x, max_y = (float(v) for v in valeur.split(","))
    except (ValueError, AttributeError):
        raise OperationInvalide("bbox attendu au format min_lon,min_lat,max_lon,max_lat.")
    return Polygon.from_bbox((min_x, min_y, max_x, max_y))


class GeoAssetViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = GeoAssetSerializer
    lookup_field = "file_id"
    lookup_url_kwarg = "file_id"

    def get_queryset(self):
        visibles = fichiers_visibles(self.request.user)
        requete = GeoAsset.objects.filter(file__in=visibles).select_related("file")
        params = self.request.query_params
        if params.get("format"):
            requete = requete.filter(geo_format=params["format"].upper())
        if params.get("srid"):
            requete = requete.filter(srid_source=params["srid"])
        if params.get("bbox"):
            requete = requete.filter(extent__intersects=bbox_depuis_parametre(params["bbox"]))
        if params.get("dossier"):
            requete = requete.filter(file__folder_id=params["dossier"])
        return requete

    @action(detail=True, methods=["get"])
    def geojson(self, request, file_id=None):
        asset = self.get_object()
        if asset.simplified_geojson:
            return Response(asset.simplified_geojson)
        if asset.extent:
            return Response(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": json.loads(asset.extent.geojson),
                            "properties": {
                                "nom": asset.file.name,
                                "emprise_seule": True,
                            },
                        }
                    ],
                }
            )
        return Response({"type": "FeatureCollection", "features": []})

    @action(detail=True, methods=["patch"], url_path="srid")
    def declarer_srid(self, request, file_id=None):
        """Corriger la projection : la seule facon de faire apparaitre sur la
        carte un fichier livre sans .prj."""
        asset = self.get_object()
        exiger(request.user, asset.file, Niveau.WRITE)
        srid = request.data.get("srid")
        if not srid:
            raise OperationInvalide("Le code EPSG est requis.")
        asset.srid_declared = int(srid)
        asset.save(update_fields=["srid_declared", "updated_at"])
        analyser_fichier(str(asset.file_id))
        asset.refresh_from_db()
        return Response(GeoAssetSerializer(asset).data)

    @action(detail=True, methods=["post"])
    def convert(self, request, file_id=None):
        asset = self.get_object()
        exiger(request.user, asset.file, Niveau.WRITE)
        job = ConversionJob.objects.create(
            file=asset.file,
            source_format=asset.geo_format,
            target_format=request.data.get("target_format", "GEOJSON").upper(),
            target_srid=request.data.get("target_srid") or None,
            requested_by=request.user,
        )
        journaliser("GEO_CONVERT", acteur=request.user, cible=asset.file,
                    cible_format=job.target_format)
        convertir(str(job.id))
        job.refresh_from_db()
        return Response(ConversionSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class ConversionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ConversionSerializer

    def get_queryset(self):
        return ConversionJob.objects.filter(requested_by=self.request.user)


class GeoLayerViewSet(viewsets.ModelViewSet):
    serializer_class = GeoLayerSerializer
    queryset = GeoLayer.objects.filter(is_active=True)

    def perform_create(self, serializer):
        serializer.save(service=self.request.user.service)


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class GeoSearchView(APIView):
    """Recherche spatiale : « quels documents concernent ce quartier ? »"""

    def get(self, request):
        requete = GeoAsset.objects.filter(
            file__in=fichiers_visibles(request.user)
        ).select_related("file")
        if request.query_params.get("bbox"):
            requete = requete.filter(
                extent__intersects=bbox_depuis_parametre(request.query_params["bbox"])
            )
        elif request.query_params.get("point"):
            try:
                lon, lat = (float(v) for v in request.query_params["point"].split(","))
            except ValueError:
                raise OperationInvalide("point attendu au format lon,lat.")
            rayon = float(request.query_params.get("rayon_m", 500))
            centre = Point(lon, lat, srid=4326)
            requete = requete.filter(extent__dwithin=(centre, rayon / 111_320))
        else:
            raise OperationInvalide("Fournissez bbox ou point.")
        return Response(GeoAssetSerializer(requete[:500], many=True).data)
