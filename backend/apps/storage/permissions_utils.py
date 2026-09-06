"""Petits utilitaires de lecture des niveaux de permission."""

from apps.sharing.models import Niveau, au_moins


def peut_ecrire(niveau: str | None) -> bool:
    return bool(niveau) and au_moins(niveau, Niveau.WRITE)


def peut_gerer(niveau: str | None) -> bool:
    return bool(niveau) and au_moins(niveau, Niveau.MANAGE)
