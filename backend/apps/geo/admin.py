from django.contrib import admin

from .models import ConversionJob, GeoAsset, GeoLayer


@admin.register(GeoAsset)
class GeoAssetAdmin(admin.ModelAdmin):
    list_display = ["file", "geo_format", "srid_source", "srid_declared", "extraction_status"]
    list_filter = ["geo_format", "extraction_status"]


admin.site.register([GeoLayer, ConversionJob])
