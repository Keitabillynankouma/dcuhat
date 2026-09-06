from __future__ import annotations

import re
import unicodedata

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.utils import timezone

from apps.common.models import SoftDeleteModel, TimeStampedModel, UUIDModel

CARACTERES_INTERDITS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def nettoyer_nom(nom: str) -> str:
    """Un nom de fichier reste lisible en francais mais ne casse aucun systeme."""
    nom = unicodedata.normalize("NFC", (nom or "").strip())
    nom = CARACTERES_INTERDITS.sub("_", nom)
    nom = nom.strip(". ")
    return nom[:255] or "sans-nom"


def segment_chemin(nom: str) -> str:
    """Segment normalise utilise dans le chemin materialise."""
    base = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-").lower()
    return base or "element"


class Kind(models.TextChoices):
    DOCUMENT = "DOCUMENT", "Document"
    CROQUIS = "CROQUIS", "Croquis"
    IMAGE = "IMAGE", "Image"
    TABLEUR = "TABLEUR", "Tableur"
    VECTEUR = "VECTEUR", "Donnees vectorielles"
    RASTER = "RASTER", "Donnees raster"
    CAO = "CAO", "Plan CAO"
    ARCHIVE = "ARCHIVE", "Archive"
    AUTRE = "AUTRE", "Autre"


#: Formats modifiables directement dans l'application.
EXTENSIONS_EDITABLES = {
    ".txt", ".md", ".csv", ".json", ".geojson", ".svg", ".gpx", ".kml", ".prj", ".log",
}


def est_editable(nom: str) -> bool:
    from pathlib import Path

    return Path(nom).suffix.lower() in EXTENSIONS_EDITABLES


class Folder(UUIDModel, TimeStampedModel, SoftDeleteModel):
    """Dossier de l'arborescence.

    Le chemin materialise (`path`) est maintenu a chaque enregistrement et a
    chaque deplacement. Il rend triviales les deux requetes les plus frequentes
    de la plateforme : « tout le sous-arbre » (permissions heritees) et
    « les changements sous ce dossier » (delta de synchronisation).
    """

    name = models.CharField("nom", max_length=255)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children"
    )
    path = models.TextField(db_index=True, editable=False, default="/")
    depth = models.PositiveIntegerField(default=0, db_index=True, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="dossiers"
    )
    service = models.ForeignKey(
        "accounts.Service", null=True, blank=True, on_delete=models.PROTECT,
        related_name="dossiers", db_index=True,
    )
    description = models.TextField(blank=True)
    color = models.CharField(max_length=20, blank=True)
    icon = models.CharField(max_length=40, blank=True)
    is_service_root = models.BooleanField(default=False)

    size_bytes = models.BigIntegerField(default=0, editable=False)
    file_count = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        verbose_name = "dossier"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "name"],
                condition=models.Q(is_deleted=False),
                name="dossier_nom_unique_par_parent",
            )
        ]
        indexes = [
            models.Index(fields=["parent", "is_deleted"]),
            models.Index(fields=["service", "is_deleted"]),
        ]

    def __str__(self):
        return self.path

    # -- chemin ------------------------------------------------------------
    def calculer_chemin(self) -> str:
        segment = segment_chemin(self.name)
        if self.parent_id is None:
            return f"/{segment}/"
        return f"{self.parent.path}{segment}/"

    def save(self, *args, **kwargs):
        self.name = nettoyer_nom(self.name)
        ancien_chemin = None
        if self.pk:
            ancien_chemin = (
                Folder.objects.filter(pk=self.pk)
                .values_list("path", flat=True)
                .first()
            )
        self.path = self.calculer_chemin()
        self.depth = self.path.count("/") - 2 if self.path != "/" else 0
        super().save(*args, **kwargs)
        if ancien_chemin and ancien_chemin != self.path:
            self._propager_chemin(ancien_chemin, self.path)

    def _propager_chemin(self, ancien: str, nouveau: str):
        """Un renommage ou un deplacement reecrit le chemin de tout le sous-arbre."""
        descendants = Folder.objects.filter(path__startswith=ancien).exclude(pk=self.pk)
        for dossier in descendants:
            dossier.path = nouveau + dossier.path[len(ancien):]
            dossier.depth = dossier.path.count("/") - 2
            models.Model.save(dossier, update_fields=["path", "depth"])

    # -- utilitaires -------------------------------------------------------
    @property
    def ancetres_paths(self) -> list[str]:
        """Chemins de tous les ancetres, du plus proche a la racine."""
        segments = [s for s in self.path.split("/") if s]
        chemins = []
        courant = ""
        for segment in segments[:-1]:
            courant += f"/{segment}"
            chemins.append(courant + "/")
        return list(reversed(chemins))

    def sous_arbre(self):
        return Folder.objects.filter(path__startswith=self.path)

    def fil_ariane(self) -> list[dict]:
        dossiers = Folder.objects.filter(path__in=self.ancetres_paths).order_by("depth")
        fil = [{"id": str(d.id), "name": d.name, "path": d.path} for d in dossiers]
        fil.append({"id": str(self.id), "name": self.name, "path": self.path})
        return fil

    def mettre_a_la_corbeille(self, par):
        maintenant = timezone.now()
        sous_arbre = self.sous_arbre()
        File.objects.filter(folder__in=sous_arbre, is_deleted=False).update(
            is_deleted=True, deleted_at=maintenant, deleted_by=par
        )
        sous_arbre.update(is_deleted=True, deleted_at=maintenant, deleted_by=par)

    def restaurer(self):
        sous_arbre = self.sous_arbre()
        File.objects.filter(folder__in=sous_arbre, is_deleted=True).update(
            is_deleted=False, deleted_at=None, deleted_by=None
        )
        sous_arbre.update(is_deleted=False, deleted_at=None, deleted_by=None)


class Tag(UUIDModel, TimeStampedModel):
    name = models.CharField(max_length=60)
    service = models.ForeignKey(
        "accounts.Service", null=True, blank=True, on_delete=models.CASCADE,
        related_name="tags",
    )
    color = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = "etiquette"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["service", "name"], name="tag_unique_service")
        ]

    def __str__(self):
        return self.name


class File(UUIDModel, TimeStampedModel, SoftDeleteModel):
    name = models.CharField("nom", max_length=255)
    folder = models.ForeignKey(Folder, on_delete=models.CASCADE, related_name="files")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="fichiers"
    )
    service = models.ForeignKey(
        "accounts.Service", null=True, blank=True, on_delete=models.PROTECT,
        related_name="fichiers", db_index=True,
    )
    current_version = models.ForeignKey(
        "storage.FileVersion", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    mime_type = models.CharField(max_length=150, blank=True)
    kind = models.CharField(
        max_length=20, choices=Kind.choices, default=Kind.AUTRE, db_index=True
    )
    size_bytes = models.BigIntegerField(default=0)
    description = models.TextField(blank=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name="fichiers")

    is_locked = models.BooleanField(default=False)
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    locked_at = models.DateTimeField(null=True, blank=True)

    extracted_text = models.TextField(blank=True, editable=False)
    search_vector = SearchVectorField(null=True, editable=False)

    class Meta:
        verbose_name = "fichier"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["folder", "name"],
                condition=models.Q(is_deleted=False),
                name="fichier_nom_unique_par_dossier",
            )
        ]
        indexes = [
            models.Index(fields=["folder", "is_deleted", "name"]),
            models.Index(fields=["kind", "is_deleted"]),
            GinIndex(fields=["search_vector"], name="fichier_recherche_gin"),
        ]

    def __str__(self):
        return f"{self.folder.path}{self.name}"

    def save(self, *args, **kwargs):
        self.name = nettoyer_nom(self.name)
        super().save(*args, **kwargs)

    @property
    def chemin_complet(self) -> str:
        return f"{self.folder.path}{self.name}"

    @property
    def est_geospatial(self) -> bool:
        return self.kind in (Kind.VECTEUR, Kind.RASTER, Kind.CAO)

    def mettre_a_la_corbeille(self, par):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = par
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_at"])

    def restaurer(self):
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_at"])

    def verrouiller(self, par):
        self.is_locked = True
        self.locked_by = par
        self.locked_at = timezone.now()
        self.save(update_fields=["is_locked", "locked_by", "locked_at", "updated_at"])

    def deverrouiller(self):
        self.is_locked = False
        self.locked_by = None
        self.locked_at = None
        self.save(update_fields=["is_locked", "locked_by", "locked_at", "updated_at"])


class Origine(models.TextChoices):
    WEB = "WEB", "Interface web"
    SYNC_OFFLINE = "SYNC_OFFLINE", "Synchronisation hors ligne"
    IMPORT = "IMPORT", "Import en masse"


class FileVersion(UUIDModel, TimeStampedModel):
    """Une version d'un fichier. Une modification n'ecrase jamais la precedente."""

    file = models.ForeignKey(File, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    storage_key = models.CharField(max_length=500)
    size_bytes = models.BigIntegerField(default=0)
    checksum_sha256 = models.CharField(max_length=64, db_index=True)
    mime_type = models.CharField(max_length=150, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    comment = models.CharField(max_length=500, blank=True)
    origin = models.CharField(max_length=20, choices=Origine.choices, default=Origine.WEB)
    client_id = models.UUIDField(null=True, blank=True)
    is_conflict_copy = models.BooleanField(default=False)

    class Meta:
        verbose_name = "version"
        ordering = ["-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["file", "version_number"], name="version_unique_par_fichier"
            )
        ]

    def __str__(self):
        return f"{self.file.name} v{self.version_number}"


class FileMetadata(UUIDModel, TimeStampedModel):
    """Metadonnee libre ou champ metier normalise."""

    class Source(models.TextChoices):
        AUTO = "AUTO", "Extraite automatiquement"
        MANUEL = "MANUEL", "Saisie par un agent"

    file = models.ForeignKey(File, on_delete=models.CASCADE, related_name="metadata")
    key = models.CharField(max_length=100, db_index=True)
    value = models.TextField(blank=True)
    value_type = models.CharField(max_length=20, default="texte")
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUEL)

    class Meta:
        verbose_name = "metadonnee"
        constraints = [
            models.UniqueConstraint(fields=["file", "key"], name="metadonnee_unique")
        ]
        indexes = [models.Index(fields=["key", "value"])]


#: Champs metier attendus par la Direction, proposes dans l'interface.
CHAMPS_METIER = [
    ("reference_dossier", "Reference du dossier"),
    ("numero_parcelle", "Numero de parcelle"),
    ("section_cadastrale", "Section cadastrale"),
    ("quartier", "Quartier / secteur"),
    ("demandeur", "Demandeur"),
    ("date_depot", "Date de depot"),
    ("date_decision", "Date de decision"),
    ("type_acte", "Type d'acte"),
    ("statut_instruction", "Statut de l'instruction"),
]


class Comment(UUIDModel, TimeStampedModel):
    file = models.ForeignKey(File, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="commentaires"
    )
    body = models.TextField()
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="reponses"
    )
    is_deleted = models.BooleanField(default=False)

    class Meta:
        verbose_name = "commentaire"
        ordering = ["created_at"]


class UploadSession(UUIDModel, TimeStampedModel):
    """Televersement fragmente : sur une liaison instable, seul le fragment
    perdu est reemis."""

    class Statut(models.TextChoices):
        EN_COURS = "EN_COURS", "En cours"
        TERMINE = "TERMINE", "Termine"
        ANNULE = "ANNULE", "Annule"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="televersements"
    )
    folder = models.ForeignKey(Folder, on_delete=models.CASCADE, related_name="+")
    file = models.ForeignKey(
        File, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    filename = models.CharField(max_length=255)
    total_size = models.BigIntegerField()
    chunk_size = models.PositiveIntegerField()
    total_chunks = models.PositiveIntegerField()
    received_chunks = models.JSONField(default=list)
    checksum_sha256 = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=20, choices=Statut.choices, default=Statut.EN_COURS)
    comment = models.CharField(max_length=500, blank=True)
    client_id = models.UUIDField(null=True, blank=True)

    class Meta:
        verbose_name = "session de televersement"

    @property
    def complet(self) -> bool:
        return len(set(self.received_chunks)) >= self.total_chunks

    @property
    def manquants(self) -> list[int]:
        recus = set(self.received_chunks)
        return [n for n in range(1, self.total_chunks + 1) if n not in recus]


class Brouillon(UUIDModel, TimeStampedModel):
    """Travail en cours sur un fichier, sauvegarde automatiquement.

    Le brouillon est la piece qui rend la sauvegarde automatique compatible
    avec le versionnement : ecrire une version toutes les deux secondes
    rendrait l'historique illisible et ferait exploser le stockage. La frappe
    de l'agent va donc dans une seule ligne, ecrasee a chaque fois ; une
    version n'est creee qu'a la publication — explicite, ou automatique apres
    un temps de travail.

    Un brouillon appartient a un agent : deux personnes qui editent le meme
    fichier ne s'ecrasent pas mutuellement, elles produisent deux versions que
    le chef de service arbitrera comme un conflit ordinaire.
    """

    file = models.ForeignKey(File, on_delete=models.CASCADE, related_name="brouillons")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="brouillons"
    )
    contenu = models.TextField(blank=True)
    base_version = models.PositiveIntegerField(default=0)
    derniere_frappe = models.DateTimeField(auto_now=True)
    publie_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "brouillon"
        ordering = ["-derniere_frappe"]
        constraints = [
            models.UniqueConstraint(
                fields=["file", "author"], name="brouillon_unique_par_agent"
            )
        ]

    def __str__(self):
        return f"Brouillon de {self.author} sur {self.file.name}"

    @property
    def taille_octets(self) -> int:
        return len(self.contenu.encode("utf-8"))
