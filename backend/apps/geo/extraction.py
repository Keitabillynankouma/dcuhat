"""Extraction des metadonnees geospatiales.

On s'appuie sur GDAL/OGR via GeoDjango (django.contrib.gis.gdal) plutot que sur
une bibliotheque supplementaire : GDAL est deja requis par PostGIS et couvre
tous les formats du cahier des charges.

Principe directeur : **aucune projection n'est devinee silencieusement**. Une
emprise fausse sur une carte communale est plus dangereuse qu'une emprise
absente ; en cas de doute, le statut passe a PARTIAL et l'agent est invite a
declarer le systeme de projection.
"""

from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

from django.contrib.gis.geos import GEOSGeometry, Polygon

EXTENSIONS_FORMAT = {
    ".shp": "SHP",
    ".geojson": "GEOJSON",
    ".json": "GEOJSON",
    ".tif": "GEOTIFF",
    ".tiff": "GEOTIFF",
    ".kml": "KML",
    ".kmz": "KMZ",
    ".gpx": "GPX",
    ".dxf": "DXF",
    ".dwg": "DWG",
    ".gpkg": "GPKG",
}


class ResultatExtraction(dict):
    """Dictionnaire de resultat, avec les cles attendues par GeoAsset."""


def format_geospatial(nom: str) -> str | None:
    return EXTENSIONS_FORMAT.get(Path(nom).suffix.lower())


def _preparer_source(chemin: Path, nom: str) -> tuple[Path, tempfile.TemporaryDirectory | None]:
    """Un Shapefile arrive souvent zippe : on le decompresse dans un dossier
    temporaire et on pointe sur le .shp."""
    if zipfile.is_zipfile(chemin):
        dossier = tempfile.TemporaryDirectory(prefix="dcuhat-geo-")
        with zipfile.ZipFile(chemin) as archive:
            archive.extractall(dossier.name)
        candidats = list(Path(dossier.name).rglob("*.shp")) or list(
            Path(dossier.name).rglob("*.gpkg")
        )
        if candidats:
            return candidats[0], dossier
        dossier.cleanup()
    return chemin, None


def extraire_vecteur(chemin: Path) -> ResultatExtraction:
    from django.contrib.gis.gdal import DataSource

    source = DataSource(str(chemin))
    couches, total, types, schema = [], 0, set(), {}
    srid = None
    enveloppe = None

    for couche in source:
        couches.append(couche.name)
        total += len(couche)
        types.add(couche.geom_type.name)
        if couche.srs is not None and srid is None:
            try:
                srid = couche.srs.srid
            except Exception:
                srid = None
        schema[couche.name] = {
            nom: str(champ) for nom, champ in zip(couche.fields, couche.field_types)
        }
        try:
            etendue = couche.extent
            boite = (etendue.min_x, etendue.min_y, etendue.max_x, etendue.max_y)
            enveloppe = boite if enveloppe is None else (
                min(enveloppe[0], boite[0]),
                min(enveloppe[1], boite[1]),
                max(enveloppe[2], boite[2]),
                max(enveloppe[3], boite[3]),
            )
        except Exception:
            pass

    resultat = ResultatExtraction(
        srid_source=srid,
        feature_count=total,
        geometry_type=(types.pop() if len(types) == 1 else "MIXED") if types else "",
        layer_names=couches,
        attributes_schema=schema,
    )
    if enveloppe:
        resultat["extent_brute"] = enveloppe
    return resultat


def extraire_raster(chemin: Path) -> ResultatExtraction:
    from django.contrib.gis.gdal import GDALRaster

    raster = GDALRaster(str(chemin))
    largeur, hauteur = raster.width, raster.height
    origine_x, origine_y = raster.origin.x, raster.origin.y
    pas_x, pas_y = raster.scale.x, raster.scale.y
    enveloppe = (
        min(origine_x, origine_x + largeur * pas_x),
        min(origine_y, origine_y + hauteur * pas_y),
        max(origine_x, origine_x + largeur * pas_x),
        max(origine_y, origine_y + hauteur * pas_y),
    )
    srid = None
    try:
        srid = raster.srs.srid
    except Exception:
        srid = None
    return ResultatExtraction(
        srid_source=srid,
        raster_width=largeur,
        raster_height=hauteur,
        raster_bands=len(raster.bands),
        pixel_size_x=pas_x,
        pixel_size_y=pas_y,
        geometry_type="RASTER",
        extent_brute=enveloppe,
    )


def emprise_wgs84(enveloppe, srid: int | None):
    """Reprojette l'emprise en WGS84. Sans SRID connu, on ne produit rien."""
    if enveloppe is None or srid is None:
        return None, None
    min_x, min_y, max_x, max_y = enveloppe
    if min_x == max_x:
        max_x += 1e-9
    if min_y == max_y:
        max_y += 1e-9
    polygone = Polygon.from_bbox((min_x, min_y, max_x, max_y))
    polygone.srid = srid
    if srid != 4326:
        polygone.transform(4326)
    return polygone, polygone.centroid


def geojson_simplifie(chemin: Path, srid: int | None, tolerance: float, max_entites: int):
    """Geometrie allegee pour l'affichage carte.

    Au-dela de `max_entites`, on ne renvoie rien : la couche sera servie en
    tuiles vectorielles par PostGIS plutot qu'en un seul GeoJSON de 40 Mo.
    """
    from django.contrib.gis.gdal import DataSource

    try:
        source = DataSource(str(chemin))
    except Exception:
        return None
    entites = []
    for couche in source:
        if len(couche) > max_entites:
            return None
        for entite in couche:
            geometrie = entite.geom
            if geometrie is None:
                continue
            try:
                geos = GEOSGeometry(geometrie.wkt, srid=srid or 4326)
                if (srid or 4326) != 4326:
                    geos.transform(4326)
                geos = geos.simplify(tolerance, preserve_topology=True)
                entites.append(
                    {
                        "type": "Feature",
                        "geometry": json.loads(geos.geojson),
                        "properties": {
                            champ: str(entite.get(champ)) for champ in couche.fields[:10]
                        },
                    }
                )
            except Exception:
                continue
    if not entites:
        return None
    return {"type": "FeatureCollection", "features": entites}


def analyser(chemin_source: Path, nom: str, *, tolerance=0.00005, max_entites=5000) -> dict:
    """Point d'entree : renvoie un dictionnaire pret pour `GeoAsset`."""
    format_detecte = format_geospatial(nom)
    if format_detecte is None:
        return {"geo_format": None}

    chemin, temporaire = _preparer_source(Path(chemin_source), nom)
    resultat: dict = {"geo_format": format_detecte, "extraction_status": "OK"}
    try:
        if format_detecte == "GEOTIFF":
            resultat.update(extraire_raster(chemin))
        else:
            resultat.update(extraire_vecteur(chemin))

        srid = resultat.get("srid_source")
        enveloppe = resultat.pop("extent_brute", None)
        if srid is None:
            resultat["extraction_status"] = "PARTIAL"
            resultat["extraction_error"] = (
                "Systeme de projection introuvable. Declarez-le manuellement "
                "pour que le fichier apparaisse sur la carte."
            )
        else:
            emprise, centre = emprise_wgs84(enveloppe, srid)
            resultat["extent"] = emprise
            resultat["centroid"] = centre
            if format_detecte != "GEOTIFF":
                resultat["simplified_geojson"] = geojson_simplifie(
                    chemin, srid, tolerance, max_entites
                )
    except Exception as erreur:  # pragma: no cover - depend du fichier
        resultat["extraction_status"] = "FAILED"
        resultat["extraction_error"] = str(erreur)[:2000]
    finally:
        if temporaire is not None:
            temporaire.cleanup()
    return resultat
