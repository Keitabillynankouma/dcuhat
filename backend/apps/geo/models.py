from __future__ import annotations

from django.conf import settings
from django.contrib.gis.db import models as gis
from django.db import models

from apps.common.models import TimeStampedModel, UUIDModel


class GeoFormat(models.TextChoices):
    SHP = "SHP", "Shapefile"
    GEOJSON = "GEOJSON", "GeoJSON"
    GEOTIFF = "GEOTIFF", "GeoTIFF"
    KML = "KML", "KML"
    KMZ = "KMZ", "KMZ"
    GPX = "GPX", "GPX"
    DXF = "DXF", "DXF"
    DWG = "DWG", "DWG"
    GPKG = "GPKG", "GeoPackage"


class StatutExtraction(models.TextChoices):
    PENDING = "PENDING", "En attente"
    OK = "OK", "Complete"
    PARTIAL = "PARTIAL", "Partielle"
    FAILED = "FAILED", "Echouee"


class GeoAsset(TimeStampedModel):
    """Metadonnees geospatiales d'un fichier.

    L'emprise est systematiquement reprojetee en WGS84 (EPSG:4326) avant
    stockage : c'est ce qui rend comparables des leves deposes dans des
    projections differentes et ce qui permet une seule requete spatiale.
    """

    file = models.OneToOneField(
        "storage.File", primary_key=True, on_delete=models.CASCADE, related_name="geo"
    )
    geo_format = models.CharField(max_length=10, choices=GeoFormat.choices)
    srid_source = models.IntegerField(null=True, blank=True)
    srid_declared = models.IntegerField(
        null=True, blank=True,
        help_text="Projection corrigee manuellement lorsque la detection echoue.",
    )
    extent = gis.PolygonField(srid=4326, null=True, blank=True, spatial_index=True)
    centroid = gis.PointField(srid=4326, null=True, blank=True, spatial_index=True)
    geometry_type = models.CharField(max_length=20, blank=True)
    feature_count = models.IntegerField(null=True, blank=True)
    layer_names = models.JSONField(default=list, blank=True)
    attributes_schema = models.JSONField(default=dict, blank=True)

    raster_width = models.IntegerField(null=True, blank=True)
    raster_height = models.IntegerField(null=True, blank=True)
    raster_bands = models.IntegerField(null=True, blank=True)
    pixel_size_x = models.FloatField(null=True, blank=True)
    pixel_size_y = models.FloatField(null=True, blank=True)

    preview_key = models.CharField(max_length=500, blank=True)
    simplified_geojson = models.JSONField(null=True, blank=True)

    extraction_status = models.CharField(
        max_length=10, choices=StatutExtraction.choices, default=StatutExtraction.PENDING
    )
    extraction_error = models.TextField(blank=True)
    extracted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "donnee geospatiale"

    def __str__(self):
        return f"{self.file.name} ({self.geo_format})"

    @property
    def srid_effectif(self):
        return self.srid_declared or self.srid_source

    @property
    def echelle_pixel(self):
        if self.pixel_size_x:
            return abs(self.pixel_size_x)
        return None


class GeoLayer(UUIDModel, TimeStampedModel):
    """Couche de reference communale : limites de quartiers, zonage du plan
    d'urbanisme, reseau viaire."""

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    service = models.ForeignKey(
        "accounts.Service", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="couches",
    )
    source_file = models.ForeignKey(
        "storage.File", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="couches",
    )
    style = models.JSONField(default=dict, blank=True)
    z_index = models.IntegerField(default=0)
    min_zoom = models.PositiveSmallIntegerField(default=0)
    max_zoom = models.PositiveSmallIntegerField(default=22)
    is_public = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "couche cartographique"
        ordering = ["z_index", "name"]

    def __str__(self):
        return self.name


class ConversionJob(UUIDModel, TimeStampedModel):
    class Statut(models.TextChoices):
        PENDING = "PENDING", "En attente"
        RUNNING = "RUNNING", "En cours"
        DONE = "DONE", "Terminee"
        FAILED = "FAILED", "Echouee"

    file = models.ForeignKey(
        "storage.File", on_delete=models.CASCADE, related_name="conversions"
    )
    source_format = models.CharField(max_length=10)
    target_format = models.CharField(max_length=10, choices=GeoFormat.choices)
    target_srid = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Statut.choices, default=Statut.PENDING)
    result_file = models.ForeignKey(
        "storage.File", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="conversions_source",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    error = models.TextField(blank=True)

    class Meta:
        verbose_name = "conversion"
        ordering = ["-created_at"]
