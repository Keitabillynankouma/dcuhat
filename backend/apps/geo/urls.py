from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("assets", views.GeoAssetViewSet, basename="geo-asset")
router.register("conversions", views.ConversionViewSet, basename="geo-conversion")
router.register("layers", views.GeoLayerViewSet, basename="geo-layer")

urlpatterns = [
    path("search/", views.GeoSearchView.as_view(), name="geo-search"),
    path("", include(router.urls)),
]
