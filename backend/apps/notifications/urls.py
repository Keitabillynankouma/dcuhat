from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("notifications", views.NotificationViewSet, basename="notification")
router.register(
    "notification-preferences",
    views.NotificationPreferenceViewSet,
    basename="notification-preference",
)

urlpatterns = [path("", include(router.urls))]
