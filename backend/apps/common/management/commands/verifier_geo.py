"""Verifie que GDAL et GEOS sont accessibles, et dit lesquels seront utilises.

    python manage.py verifier_geo

A lancer en premier quand la plateforme refuse de demarrer sur une nouvelle
machine ou un nouvel hebergement : c'est presque toujours de la que vient le
probleme.
"""

from django.core.management.base import BaseCommand

from apps.common.geolibs import diagnostic


class Command(BaseCommand):
    help = "Diagnostique la detection des bibliotheques geospatiales."

    def handle(self, *args, **options):
        infos = diagnostic()

        self.stdout.write(self.style.MIGRATE_HEADING("Detection"))
        for cle in ("systeme", "python"):
            self.stdout.write(f"  {cle:<22} {infos[cle]}")
        self.stdout.write(
            f"  {'GDAL_LIBRARY_PATH':<22} {infos['gdal_variable'] or '(non definie)'}"
        )
        self.stdout.write(
            f"  {'GEOS_LIBRARY_PATH':<22} {infos['geos_variable'] or '(non definie)'}"
        )
        self.stdout.write(
            f"  {'GDAL retenu':<22} {infos['gdal'] or '(recherche laissee a Django)'}"
        )
        self.stdout.write(
            f"  {'GEOS retenu':<22} {infos['geos'] or '(recherche laissee a Django)'}"
        )

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Chargement effectif"))
        try:
            from django.contrib.gis.gdal import gdal_full_version, gdal_version
            from django.contrib.gis.geos import geos_version

            self.stdout.write(
                self.style.SUCCESS(f"  GDAL {gdal_version().decode()} charge")
            )
            self.stdout.write(f"  {gdal_full_version().decode()}")
            self.stdout.write(
                self.style.SUCCESS(f"  GEOS {geos_version().decode()} charge")
            )
        except Exception as erreur:
            self.stdout.write(self.style.ERROR(f"  Echec : {erreur}"))
            self.stdout.write("")
            self.stdout.write(
                "  Pistes : sous Windows, installez le bundle PostGIS ; sur un "
                "hebergement sans acces systeme, installez les dependances avec "
                "requirements-sans-docker.txt."
            )
            return

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Base de donnees"))
        try:
            from django.db import connection

            with connection.cursor() as curseur:
                curseur.execute("SELECT PostGIS_Version();")
                self.stdout.write(
                    self.style.SUCCESS(f"  PostGIS {curseur.fetchone()[0]}")
                )
        except Exception as erreur:
            self.stdout.write(self.style.ERROR(f"  Base injoignable : {erreur}"))
