"""Abstraction du stockage des contenus binaires.

Deux implementations : un stockage local (developpement, serveur communal sans
MinIO) et un stockage objet S3-compatible (MinIO, Amazon S3). Le reste du code
ne connait que l'interface ci-dessous, ce qui permet de basculer de l'un a
l'autre sans toucher au metier.
"""

from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO, Iterator

from django.conf import settings


def cle_objet(service_code: str, file_id, version: int, nom: str) -> str:
    """Cle de stockage : lisible, triable, sans collision."""
    extension = Path(nom).suffix.lower()
    return f"{service_code or 'commun'}/{file_id}/v{version}{extension}"


def sha256_flux(flux: BinaryIO, taille_bloc: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    flux.seek(0)
    while bloc := flux.read(taille_bloc):
        digest.update(bloc)
    flux.seek(0)
    return digest.hexdigest()


class StockageObjet:
    def ecrire(self, cle: str, flux: BinaryIO) -> int:
        raise NotImplementedError

    def lire(self, cle: str) -> BinaryIO:
        raise NotImplementedError

    def flux(self, cle: str, taille_bloc: int = 1024 * 256) -> Iterator[bytes]:
        raise NotImplementedError

    def supprimer(self, cle: str) -> None:
        raise NotImplementedError

    def existe(self, cle: str) -> bool:
        raise NotImplementedError

    def url_temporaire(self, cle: str, nom_telechargement: str = "") -> str | None:
        """URL pre-signee, ou None si le backend ne sait pas en produire."""
        return None


class StockageLocal(StockageObjet):
    def __init__(self, racine: Path | None = None):
        self.racine = Path(racine or settings.OBJECT_STORAGE_LOCAL_ROOT)
        self.racine.mkdir(parents=True, exist_ok=True)

    def _chemin(self, cle: str) -> Path:
        chemin = (self.racine / cle).resolve()
        racine = self.racine.resolve()
        if not str(chemin).startswith(str(racine)):
            raise ValueError("Cle de stockage invalide.")
        return chemin

    def ecrire(self, cle: str, flux: BinaryIO) -> int:
        chemin = self._chemin(cle)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        temporaire = chemin.with_suffix(chemin.suffix + f".{uuid.uuid4().hex}.tmp")
        flux.seek(0)
        with open(temporaire, "wb") as sortie:
            shutil.copyfileobj(flux, sortie, length=1024 * 1024)
        temporaire.replace(chemin)
        return chemin.stat().st_size

    def lire(self, cle: str) -> BinaryIO:
        return open(self._chemin(cle), "rb")

    def flux(self, cle: str, taille_bloc: int = 1024 * 256) -> Iterator[bytes]:
        with open(self._chemin(cle), "rb") as entree:
            while bloc := entree.read(taille_bloc):
                yield bloc

    def supprimer(self, cle: str) -> None:
        chemin = self._chemin(cle)
        if chemin.exists():
            chemin.unlink()

    def existe(self, cle: str) -> bool:
        return self._chemin(cle).exists()

    def chemin_local(self, cle: str) -> Path:
        return self._chemin(cle)


class StockageS3(StockageObjet):
    def __init__(self):
        import boto3
        from botocore.config import Config

        self.bucket = settings.S3_BUCKET
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
            # Adressage par chemin : impose par MinIO et par le point d'acces
            # S3 de Supabase. Sans lui, boto3 construit une adresse de la forme
            # `https://mon-bucket.<hote>/...` qui n'existe pas chez eux.
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )

    def ecrire(self, cle: str, flux: BinaryIO) -> int:
        flux.seek(0, 2)
        taille = flux.tell()
        flux.seek(0)
        self.client.upload_fileobj(flux, self.bucket, cle)
        return taille

    def lire(self, cle: str) -> BinaryIO:
        objet = self.client.get_object(Bucket=self.bucket, Key=cle)
        return objet["Body"]

    def flux(self, cle: str, taille_bloc: int = 1024 * 256) -> Iterator[bytes]:
        corps = self.lire(cle)
        while bloc := corps.read(taille_bloc):
            yield bloc

    def supprimer(self, cle: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=cle)

    def existe(self, cle: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=cle)
            return True
        except ClientError:
            return False

    def url_temporaire(self, cle: str, nom_telechargement: str = "") -> str:
        params = {"Bucket": self.bucket, "Key": cle}
        if nom_telechargement:
            params["ResponseContentDisposition"] = (
                f'attachment; filename="{nom_telechargement}"'
            )
        return self.client.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=settings.S3_PRESIGNED_TTL
        )


_instance: StockageObjet | None = None


def stockage() -> StockageObjet:
    global _instance
    if _instance is None:
        if settings.OBJECT_STORAGE_BACKEND == "s3":
            _instance = StockageS3()
        else:
            _instance = StockageLocal()
    return _instance


def reinitialiser_stockage() -> None:
    """Utilise par les tests pour repartir d'un stockage propre."""
    global _instance
    _instance = None
