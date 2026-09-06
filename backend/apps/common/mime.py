"""Detection du type reel d'un fichier.

L'extension n'est jamais la source de verite : un `.pdf` peut etre un
executable renomme. On lit les premiers octets (magic bytes) et on ne retient
l'extension que pour departager des formats textuels indistinguables.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

SIGNATURES = [
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
    (b"PK\x03\x04", "application/zip"),
    (b"\x00\x00\x27\x0a", "application/x-shapefile"),
    (b"AC10", "image/vnd.dwg"),
]

EXTENSIONS_ZIP = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".kmz": "application/vnd.google-earth.kmz",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
}

EXTENSIONS_TEXTE = {
    ".svg": "image/svg+xml",
    ".geojson": "application/geo+json",
    ".json": "application/json",
    ".kml": "application/vnd.google-earth.kml+xml",
    ".gpx": "application/gpx+xml",
    ".dxf": "image/vnd.dxf",
    ".csv": "text/csv",
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".prj": "text/plain",
}

# Types formellement interdits au televersement.
TYPES_INTERDITS = {
    "application/x-msdownload",
    "application/x-dosexec",
    "application/x-executable",
    "application/x-sharedlib",
    "application/x-mach-binary",
}

SIGNATURES_INTERDITES = [b"MZ", b"\x7fELF", b"\xca\xfe\xba\xbe"]


def detecter_mime(chemin_ou_octets, nom: str = "") -> str:
    if isinstance(chemin_ou_octets, (str, Path)):
        with open(chemin_ou_octets, "rb") as flux:
            entete = flux.read(512)
    else:
        entete = bytes(chemin_ou_octets[:512])

    extension = Path(nom).suffix.lower()

    for signature, mime in SIGNATURES:
        if entete.startswith(signature):
            if mime == "application/zip" and extension in EXTENSIONS_ZIP:
                return EXTENSIONS_ZIP[extension]
            return mime

    if extension in EXTENSIONS_TEXTE:
        return EXTENSIONS_TEXTE[extension]

    devine, _ = mimetypes.guess_type(nom or "fichier")
    return devine or "application/octet-stream"


def est_executable(chemin_ou_octets) -> bool:
    if isinstance(chemin_ou_octets, (str, Path)):
        with open(chemin_ou_octets, "rb") as flux:
            entete = flux.read(8)
    else:
        entete = bytes(chemin_ou_octets[:8])
    return any(entete.startswith(sig) for sig in SIGNATURES_INTERDITES)


KIND_PAR_MIME = {
    "application/pdf": "DOCUMENT",
    "application/msword": "DOCUMENT",
    "text/plain": "DOCUMENT",
    "text/markdown": "DOCUMENT",
    "image/png": "IMAGE",
    "image/jpeg": "IMAGE",
    "image/gif": "IMAGE",
    "image/webp": "IMAGE",
    "text/csv": "TABLEUR",
    "image/vnd.dxf": "CAO",
    "image/vnd.dwg": "CAO",
    "image/tiff": "RASTER",
    "application/geo+json": "VECTEUR",
    "application/vnd.google-earth.kml+xml": "VECTEUR",
    "application/vnd.google-earth.kmz": "VECTEUR",
    "application/gpx+xml": "VECTEUR",
    "application/x-shapefile": "VECTEUR",
}

EXTENSIONS_VECTEUR = {".shp", ".geojson", ".kml", ".kmz", ".gpx", ".gpkg"}
EXTENSIONS_RASTER = {".tif", ".tiff", ".geotiff"}
EXTENSIONS_CAO = {".dxf", ".dwg"}


def deduire_kind(mime: str, nom: str = "") -> str:
    extension = Path(nom).suffix.lower()
    if extension == ".svg":
        return "CROQUIS"
    if extension in EXTENSIONS_VECTEUR:
        return "VECTEUR"
    if extension in EXTENSIONS_RASTER:
        return "RASTER"
    if extension in EXTENSIONS_CAO:
        return "CAO"
    if mime in KIND_PAR_MIME:
        return KIND_PAR_MIME[mime]
    if mime.startswith("image/"):
        return "IMAGE"
    if "spreadsheet" in mime or "excel" in mime:
        return "TABLEUR"
    if "word" in mime or "document" in mime or mime.startswith("text/"):
        return "DOCUMENT"
    return "AUTRE"
