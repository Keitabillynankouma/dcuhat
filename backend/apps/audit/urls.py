from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("activity", views.ActivityLogViewSet, basename="activity")

urlpatterns = [path("", include(router.urls))]
