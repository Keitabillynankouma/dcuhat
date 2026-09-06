from rest_framework.permissions import BasePermission

from .models import Role


class EstAdministrateur(BasePermission):
    message = "Reserve aux administrateurs de la plateforme."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.est_admin)


class EstAdministrateurOuChefService(BasePermission):
    message = "Reserve aux administrateurs et chefs de service."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.est_admin or user.role == Role.CHEF_SERVICE)
        )


class LectureSeulePourLecteur(BasePermission):
    """Un compte LECTEUR ou INVITE ne peut pas ecrire, quel que soit le noeud."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return user.role not in (Role.LECTEUR, Role.INVITE)
