from __future__ import annotations

import json

from rest_framework import serializers

from .models import ConversionJob, GeoAsset, GeoLayer


class GeoAssetSerializer(serializers.ModelSerializer):
    fichier_nom = serializers.CharField(source="file.name", read_only=True)
    srid_effectif = serializers.IntegerField(read_only=True)
    emprise = serializers.SerializerMethodField()
    centre = serializers.SerializerMethodField()

    class Meta:
        model = GeoAsset
        fields = [
            "file", "fichier_nom", "geo_format", "srid_source", "srid_declared",
            "srid_effectif", "emprise", "centre", "geometry_type", "feature_count",
            "layer_names", "attributes_schema", "raster_width", "raster_height",
            "raster_bands", "pixel_size_x", "pixel_size_y", "extraction_status",
            "extraction_error", "extracted_at",
        ]
        read_only_fields = [
            champ for champ in fields if champ != "srid_declared"
        ]

    def get_emprise(self, obj):
        return json.loads(obj.extent.geojson) if obj.extent else None

    def get_centre(self, obj):
        return json.loads(obj.centroid.geojson) if obj.centroid else None


class GeoLayerSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeoLayer
        fields = [
            "id", "name", "description", "service", "source_file", "style",
            "z_index", "min_zoom", "max_zoom", "is_public", "is_active",
        ]


class ConversionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversionJob
        fields = [
            "id", "file", "source_format", "target_format", "target_srid",
            "status", "result_file", "error", "created_at",
        ]
        read_only_fields = ["id", "source_format", "status", "result_file", "error", "created_at"]
