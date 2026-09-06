from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

api_v1 = [
    path("auth/", include("apps.accounts.urls")),
    path("", include("apps.storage.urls")),
    path("geo/", include("apps.geo.urls")),
    path("", include("apps.sharing.urls")),
    path("sync/", include("apps.sync.urls")),
    path("", include("apps.audit.urls")),
    path("", include("apps.search.urls")),
    path("", include("apps.notifications.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include((api_v1, "v1"))),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]
