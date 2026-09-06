"""Localisation des bibliotheques geospatiales GDAL et GEOS.

GeoDjango a besoin de deux bibliotheques natives, `libgdal` et `libgeos_c`.
Leur emplacement change du tout au tout selon l'environnement :

- image Docker ou serveur Linux : installees par le systeme, Django les trouve seul ;
- poste Windows : fournies par le bundle PostGIS, avec un nom de fichier qui
  change a chaque version (`libgdal-35.dll`, `libgdal-36.dll`...) ;
- hebergement sans acces systeme (Render, Koyeb en mode Python, PythonAnywhere) :
  aucune installation systeme n'est possible, mais les roues PyPI de `rasterio`
  et `shapely` embarquent ces memes bibliotheques dans `site-packages`.

Ce module cherche dans ces trois directions, dans cet ordre, et laisse Django
faire sa propre recherche s'il ne trouve rien. Il evite ainsi d'avoir a coder en
dur un chemin qui sera faux sur la machine suivante.
"""

from __future__ import annotations

import ctypes.util
import glob
import importlib
import os
import sys
from pathlib import Path


def _premier_existant(motifs: list[str]) -> str | None:
    for motif in motifs:
        for chemin in sorted(glob.glob(motif), reverse=True):
            if os.path.isfile(chemin):
                return chemin
    return None


def _dossiers_site_packages() -> list[str]:
    dossiers = []
    for chemin in sys.path:
        if chemin.endswith(("site-packages", "dist-packages")):
            dossiers.append(chemin)
    return dossiers


def _racines_windows() -> list[str]:
    racines = []
    for base in (
        r"C:\Program Files\PostgreSQL",
        r"C:\Program Files (x86)\PostgreSQL",
    ):
        racines.extend(sorted(glob.glob(os.path.join(base, "*", "bin")), reverse=True))
    racines.append(r"C:\OSGeo4W\bin")
    racines.append(r"C:\OSGeo4W64\bin")
    return [r for r in racines if os.path.isdir(r)]


def _precharger(paquet: str) -> bool:
    """Importe un paquet pour que ses bibliotheques natives soient chargees.

    Les roues de `rasterio` et `shapely` rangent GDAL, GEOS et leurs dependances
    (libcurl, libproj...) dans un dossier `*.libs`. Charger `libgdal` seul
    echouerait : ses voisines ne sont pas dans le chemin de recherche du
    systeme. Importer le paquet les met toutes en memoire au prealable.
    """
    try:
        importlib.import_module(paquet)
        return True
    except Exception:
        return False


def trouver_gdal() -> str | None:
    """Chemin complet de la bibliotheque GDAL, ou None si Django doit chercher."""
    explicite = os.environ.get("GDAL_LIBRARY_PATH")
    if explicite:
        return explicite if os.path.isfile(explicite) else None

    if os.name == "nt":
        return _premier_existant(
            [os.path.join(racine, "libgdal*.dll") for racine in _racines_windows()]
            + [os.path.join(racine, "gdal*.dll") for racine in _racines_windows()]
        )

    # Sur un systeme qui fournit GDAL (image Docker, serveur Linux), on le laisse
    # gagner : c'est la version testee avec la base PostGIS installee a cote.
    if ctypes.util.find_library("gdal"):
        return None

    # Sinon : bibliotheque embarquee dans une roue PyPI, seule option sur un
    # hebergement sans acces systeme.
    motifs = []
    for dossier in _dossiers_site_packages():
        motifs.append(os.path.join(dossier, "rasterio.libs", "libgdal*.so*"))
        motifs.append(os.path.join(dossier, "fiona.libs", "libgdal*.so*"))
    chemin = _premier_existant(motifs)
    if chemin is None:
        return None
    paquet = "rasterio" if "rasterio.libs" in chemin else "fiona"
    return chemin if _precharger(paquet) else None


def trouver_geos() -> str | None:
    """Chemin complet de la bibliotheque GEOS, ou None si Django doit chercher."""
    explicite = os.environ.get("GEOS_LIBRARY_PATH")
    if explicite:
        return explicite if os.path.isfile(explicite) else None

    if os.name == "nt":
        return _premier_existant(
            [os.path.join(racine, "libgeos_c.dll") for racine in _racines_windows()]
            + [os.path.join(racine, "geos_c.dll") for racine in _racines_windows()]
        )

    if ctypes.util.find_library("geos_c"):
        return None

    correspondances = [
        ("shapely.libs", "shapely"),
        ("rasterio.libs", "rasterio"),
        ("fiona.libs", "fiona"),
    ]
    for dossier in _dossiers_site_packages():
        for sous_dossier, paquet in correspondances:
            chemin = _premier_existant(
                [os.path.join(dossier, sous_dossier, "libgeos_c*.so*")]
            )
            if chemin and _precharger(paquet):
                return chemin
    return None


def diagnostic() -> dict:
    """Utilise par la commande `verifier_geo` pour expliquer ce qui a ete trouve."""
    return {
        "systeme": os.name,
        "gdal": trouver_gdal(),
        "geos": trouver_geos(),
        "site_packages": _dossiers_site_packages(),
        "racines_windows": _racines_windows() if os.name == "nt" else [],
        "gdal_variable": os.environ.get("GDAL_LIBRARY_PATH", ""),
        "geos_variable": os.environ.get("GEOS_LIBRARY_PATH", ""),
        "python": str(Path(sys.executable)),
    }
