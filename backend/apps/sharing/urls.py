from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("permissions", views.PermissionViewSet, basename="permission")
router.register("share-links", views.ShareLinkViewSet, basename="share-link")

urlpatterns = [
    path("share-links/<str:token>/access/", views.AccesLienView.as_view(), name="share-access"),
    path("", include(router.urls)),
]
