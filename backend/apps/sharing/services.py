"""Moteur d'evaluation des permissions.

Ordre d'evaluation (specification section 6.3), premier verdict trouve :

1. ADMIN                              -> MANAGE
2. permission explicite sur le noeud
3. permission heritee de l'ancetre le plus proche (inherit = True)
4. appartenance au service proprietaire
5. DIRECTEUR                          -> READ sur tout
6. sinon : aucun droit, et le noeud est *invisible* (404, jamais 403).
"""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Role
from apps.storage.models import File, Folder

from .models import POIDS_NIVEAU, Niveau, Permission, au_moins

AUCUN = None


def _meilleur(niveaux) -> str | None:
    niveaux = [n for n in niveaux if n]
    if not niveaux:
        return None
    return max(niveaux, key=lambda n: POIDS_NIVEAU.get(n, 0))


def _permissions_actives(filtre: Q, user) -> list[Permission]:
    maintenant = timezone.now()
    beneficiaire = Q(grantee_user=user)
    if user.service_id:
        beneficiaire |= Q(grantee_service_id=user.service_id)
    return list(
        Permission.objects.filter(filtre)
        .filter(beneficiaire)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=maintenant))
    )


def niveau_sur_dossier(user, dossier: Folder) -> str | None:
    if user is None or not user.is_authenticated:
        return None
    if user.est_admin:
        return Niveau.MANAGE

    # 2 + 3 : permission explicite sur le dossier, ou heritee d'un ancetre.
    chemins = [dossier.path] + dossier.ancetres_paths
    permissions = _permissions_actives(Q(folder__path__in=chemins), user)
    candidats = []
    for permission in permissions:
        if permission.folder.path == dossier.path or permission.inherit:
            candidats.append(permission.level)
    niveau = _meilleur(candidats)
    if niveau:
        return niveau

    # 4 : appartenance au service proprietaire du noeud.
    if dossier.service_id and user.service_id == dossier.service_id:
        return {
            Role.CHEF_SERVICE: Niveau.MANAGE,
            Role.AGENT: Niveau.WRITE,
            Role.LECTEUR: Niveau.READ,
        }.get(user.role)

    # 5 : le directeur voit tout, en lecture.
    if user.est_directeur:
        return Niveau.READ

    if dossier.owner_id == user.id:
        return Niveau.MANAGE

    return AUCUN


def niveau_sur_fichier(user, fichier: File) -> str | None:
    if user is None or not user.is_authenticated:
        return None
    if user.est_admin:
        return Niveau.MANAGE

    permissions = _permissions_actives(Q(file=fichier), user)
    niveau = _meilleur([p.level for p in permissions])
    if niveau:
        return niveau

    if fichier.owner_id == user.id:
        return Niveau.MANAGE

    # Le fichier herite du dossier qui le contient.
    return niveau_sur_dossier(user, fichier.folder)


def peut(user, noeud, requis: str) -> bool:
    if isinstance(noeud, Folder):
        niveau = niveau_sur_dossier(user, noeud)
    elif isinstance(noeud, File):
        niveau = niveau_sur_fichier(user, noeud)
    else:
        raise TypeError(f"Noeud non supporte : {type(noeud)!r}")
    return bool(niveau) and au_moins(niveau, requis)


def exiger(user, noeud, requis: str):
    """Leve l'erreur adaptee.

    Si l'agent n'a aucun droit, on repond 404 : reveler l'existence d'un
    dossier auquel on n'a pas acces est deja une fuite d'information.
    """
    from django.http import Http404

    from apps.common.exceptions import PermissionRefusee

    if isinstance(noeud, Folder):
        niveau = niveau_sur_dossier(user, noeud)
    else:
        niveau = niveau_sur_fichier(user, noeud)

    if not niveau:
        raise Http404
    if not au_moins(niveau, requis):
        raise PermissionRefusee(
            f"Droit « {requis} » requis, vous disposez de « {niveau} »."
        )
    return niveau


# ---------------------------------------------------------------------------
# Filtrage des listes
# ---------------------------------------------------------------------------
def dossiers_visibles(user):
    """QuerySet des dossiers que l'agent a le droit de voir.

    Construit en une requete : on rassemble les chemins autorises par
    permission explicite, puis on ajoute le perimetre du service.
    """
    base = Folder.objects.filter(is_deleted=False)
    if user.est_admin or user.est_directeur:
        return base

    maintenant = timezone.now()
    beneficiaire = Q(grantee_user=user)
    if user.service_id:
        beneficiaire |= Q(grantee_service_id=user.service_id)
    permissions = (
        Permission.objects.filter(folder__isnull=False)
        .filter(beneficiaire)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=maintenant))
        .select_related("folder")
    )

    condition = Q(owner=user)
    if user.service_id:
        condition |= Q(service_id=user.service_id)
    for permission in permissions:
        if permission.inherit:
            condition |= Q(path__startswith=permission.folder.path)
        else:
            condition |= Q(pk=permission.folder_id)
    return base.filter(condition)


def fichiers_visibles(user):
    base = File.objects.filter(is_deleted=False)
    if user.est_admin or user.est_directeur:
        return base
    dossiers = dossiers_visibles(user)
    maintenant = timezone.now()
    beneficiaire = Q(grantee_user=user)
    if user.service_id:
        beneficiaire |= Q(grantee_service_id=user.service_id)
    ids_fichiers = (
        Permission.objects.filter(file__isnull=False)
        .filter(beneficiaire)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=maintenant))
        .values_list("file_id", flat=True)
    )
    return base.filter(Q(folder__in=dossiers) | Q(owner=user) | Q(pk__in=ids_fichiers))
