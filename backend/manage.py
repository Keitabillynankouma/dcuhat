#!/usr/bin/env python
"""Utilitaire de ligne de commande Django pour la plateforme DCUHAT."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Django est introuvable. Activez l'environnement virtuel "
            "ou installez les dependances (pip install -r requirements.txt)."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
