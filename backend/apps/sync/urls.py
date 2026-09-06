from django.urls import path

from . import views

urlpatterns = [
    path("delta/", views.DeltaView.as_view(), name="sync-delta"),
    path("operations/", views.OperationsView.as_view(), name="sync-operations"),
    path("operations/<uuid:pk>/", views.OperationDetailView.as_view(), name="sync-operation"),
    path("conflicts/", views.ConflitsView.as_view(), name="sync-conflicts"),
    path("conflicts/<uuid:pk>/resolve/", views.ResoudreConflitView.as_view(), name="sync-resolve"),
    path("manifest/", views.ManifestView.as_view(), name="sync-manifest"),
]
