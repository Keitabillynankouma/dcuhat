from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

router = DefaultRouter()
router.register("users", views.UserViewSet, basename="user")
router.register("services", views.ServiceViewSet, basename="service")
router.register("devices", views.DeviceViewSet, basename="device")

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("refresh/", TokenRefreshView.as_view(), name="refresh"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.MeView.as_view(), name="me"),
    path("password/change/", views.ChangePasswordView.as_view(), name="password-change"),
    path("totp/", views.TotpSetupView.as_view(), name="totp"),
    path("statistiques/", views.StatistiquesView.as_view(), name="statistiques"),
    path("", include(router.urls)),
]
