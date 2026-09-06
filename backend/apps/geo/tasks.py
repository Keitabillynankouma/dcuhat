"""Traitements asynchrones : extraction, conversion, indexation.

Les fonctions sont utilisables directement (synchrones, pratique en test et en
mode « poste unique » sans Celery) et exposees comme taches Celery pour la
production.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.common.object_storage import stockage
from apps.storage.models import File

from . import extraction
from .models import ConversionJob, GeoAsset, StatutExtraction


def _telecharger_temporairement(fichier: File) -> tempfile.NamedTemporaryFile:
    suffixe = Path(fichier.name).suffix
    temporaire = tempfile.NamedTemporaryFile(suffix=suffixe, delete=False)
    with stockage().lire(fichier.current_version.storage_key) as source:
        for bloc in iter(lambda: source.read(1024 * 1024), b""):
            temporaire.write(bloc)
    temporaire.flush()
    temporaire.close()
    return temporaire


def analyser_fichier(file_id: str) -> dict:
    """Analyse un fichier apres televersement : texte indexable, et si le
    format est geospatial, emprise, projection et apercu."""
    fichier = File.objects.filter(pk=file_id).select_related("current_version").first()
    if fichier is None or fichier.current_version_id is None:
        return {"statut": "ignore"}

    indexer_texte(fichier)

    if extraction.format_geospatial(fichier.name) is None:
        return {"statut": "non_geospatial"}

    temporaire = _telecharger_temporairement(fichier)
    try:
        resultat = extraction.analyser(
            Path(temporaire.name),
            fichier.name,
            tolerance=settings.GEO_SIMPLIFY_TOLERANCE,
            max_entites=settings.GEO_MAX_FEATURES_INLINE,
        )
    finally:
        Path(temporaire.name).unlink(missing_ok=True)

    if not resultat.get("geo_format"):
        return {"statut": "non_geospatial"}

    champs = {
        cle: valeur
        for cle, valeur in resultat.items()
        if cle
        in {
            "geo_format", "srid_source", "extent", "centroid", "geometry_type",
            "feature_count", "layer_names", "attributes_schema", "raster_width",
            "raster_height", "raster_bands", "pixel_size_x", "pixel_size_y",
            "simplified_geojson", "extraction_status", "extraction_error",
        }
    }
    champs["extracted_at"] = timezone.now()
    GeoAsset.objects.update_or_create(file=fichier, defaults=champs)
    return {"statut": champs.get("extraction_status", StatutExtraction.OK)}


def indexer_texte(fichier: File) -> None:
    """Extrait le texte indexable des formats bureautiques courants."""
    texte = ""
    suffixe = Path(fichier.name).suffix.lower()
    try:
        if suffixe == ".pdf":
            from pypdf import PdfReader

            temporaire = _telecharger_temporairement(fichier)
            lecteur = PdfReader(temporaire.name)
            texte = "\n".join((page.extract_text() or "") for page in lecteur.pages[:50])
            Path(temporaire.name).unlink(missing_ok=True)
        elif suffixe == ".docx":
            import docx

            temporaire = _telecharger_temporairement(fichier)
            document = docx.Document(temporaire.name)
            texte = "\n".join(p.text for p in document.paragraphs[:2000])
            Path(temporaire.name).unlink(missing_ok=True)
        elif suffixe in (".txt", ".md", ".csv", ".geojson"):
            with stockage().lire(fichier.current_version.storage_key) as flux:
                texte = flux.read(200_000).decode("utf-8", errors="ignore")
    except Exception:  # pragma: no cover - fichier illisible
        texte = ""

    File.objects.filter(pk=fichier.pk).update(extracted_text=texte[:500_000])
    reindexer(fichier.pk)


def reindexer(file_id) -> None:
    """Recalcule le vecteur de recherche plein texte (dictionnaire francais)."""
    from django.contrib.postgres.search import SearchVector
    from django.db.models import TextField, Value
    from django.db.models.functions import Cast, Coalesce

    texte = lambda champ: Coalesce(  # noqa: E731
        Cast(champ, TextField()), Value("", output_field=TextField())
    )
    File.objects.filter(pk=file_id).update(
        search_vector=(
            SearchVector(texte("name"), weight="A", config="french")
            + SearchVector(texte("description"), weight="B", config="french")
            + SearchVector(texte("extracted_text"), weight="D", config="french")
        )
    )


def _empaqueter(sortie: Path) -> tuple[Path, str]:
    """Un Shapefile est un jeu de 3 a 8 fichiers : il ne se transporte qu'en
    archive. On ne livre un fichier nu que lorsque la conversion n'en a produit
    qu'un seul."""
    import zipfile

    produits = sorted(p for p in sortie.parent.iterdir() if p.is_file())
    if len(produits) == 1:
        return produits[0], produits[0].name
    archive = sortie.parent.parent / (sortie.stem + ".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_sortie:
        for produit in produits:
            zip_sortie.write(produit, produit.name)
    return archive, archive.name


def convertir(job_id: str) -> str:
    """Conversion entre formats geospatiaux, via ogr2ogr."""
    import subprocess

    from apps.storage import services as storage_services

    job = ConversionJob.objects.filter(pk=job_id).select_related("file").first()
    if job is None:
        return "introuvable"
    job.status = ConversionJob.Statut.RUNNING
    job.save(update_fields=["status", "updated_at"])

    extensions = {
        "GEOJSON": (".geojson", "GeoJSON"),
        "SHP": (".shp", "ESRI Shapefile"),
        "KML": (".kml", "KML"),
        "GPKG": (".gpkg", "GPKG"),
        "GPX": (".gpx", "GPX"),
        "DXF": (".dxf", "DXF"),
    }
    if job.target_format not in extensions:
        job.status = ConversionJob.Statut.FAILED
        job.error = "Format de sortie non pris en charge."
        job.save(update_fields=["status", "error", "updated_at"])
        return "format_non_supporte"

    suffixe, pilote = extensions[job.target_format]
    entree = _telecharger_temporairement(job.file)
    sortie = Path(tempfile.mkdtemp(prefix="dcuhat-conv-")) / (
        Path(job.file.name).stem + suffixe
    )
    commande = ["ogr2ogr", "-f", pilote]
    if job.target_srid:
        commande += ["-t_srs", f"EPSG:{job.target_srid}"]
    commande += [str(sortie), entree.name]

    try:
        subprocess.run(commande, check=True, capture_output=True, timeout=600)
        livrable, nom_livrable = _empaqueter(sortie)
        with open(livrable, "rb") as produit:
            nouveau, _ = storage_services.creer_ou_mettre_a_jour_fichier(
                nom=nom_livrable,
                dossier=job.file.folder,
                contenu=produit,
                auteur=job.requested_by or job.file.owner,
                commentaire=f"Conversion depuis {job.file.name}",
            )
        job.result_file = nouveau
        job.status = ConversionJob.Statut.DONE
        job.save(update_fields=["result_file", "status", "updated_at"])
        analyser_fichier(str(nouveau.id))
        return "ok"
    except subprocess.CalledProcessError as erreur:
        job.status = ConversionJob.Statut.FAILED
        job.error = (erreur.stderr or b"").decode()[:2000]
        job.save(update_fields=["status", "error", "updated_at"])
        return "echec"
    except Exception as erreur:  # pragma: no cover
        job.status = ConversionJob.Statut.FAILED
        job.error = str(erreur)[:2000]
        job.save(update_fields=["status", "error", "updated_at"])
        return "echec"
    finally:
        Path(entree.name).unlink(missing_ok=True)


# --- enveloppes Celery -----------------------------------------------------
analyser_fichier_task = shared_task(name="geo.analyser_fichier")(analyser_fichier)
convertir_task = shared_task(name="geo.convertir")(convertir)
