from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("folders", views.FolderViewSet, basename="folder")
router.register("files", views.FileViewSet, basename="file")

urlpatterns = [
    path("files/upload/simple/", views.SimpleUploadView.as_view(), name="upload-simple"),
    path("files/upload/init/", views.UploadInitView.as_view(), name="upload-init"),
    path(
        "files/upload/<uuid:upload_id>/part/<int:numero>/",
        views.UploadPartView.as_view(),
        name="upload-part",
    ),
    path(
        "files/upload/<uuid:upload_id>/complete/",
        views.UploadCompleteView.as_view(),
        name="upload-complete",
    ),
    path("files/nouveau/", views.NouveauDocumentView.as_view(), name="document-nouveau"),
    path("trash/", views.TrashView.as_view(), name="trash"),
    path("trash/<uuid:identifiant>/", views.TrashItemView.as_view(), name="trash-item"),
    path("", include(router.urls)),
]
