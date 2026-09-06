"""Edition du contenu d'un document depuis l'application.

Trois idees gouvernent ce module.

**Le brouillon absorbe la frappe.** La sauvegarde automatique ecrit dans une
ligne unique, ecrasee a chaque fois. Aucune version n'est creee tant que
l'agent n'a pas fini : l'historique reste lisible et le stockage ne gonfle pas.

**Une version est tout de meme creee regulierement.** Si l'agent travaille une
heure sans rien publier, une coupure de courant ne doit pas lui couter une
heure. Au-dela de `EDITION_INTERVALLE_VERSION_MINUTES` depuis la derniere
version, la sauvegarde automatique en publie une d'elle-meme.

**Le brouillon appartient a un agent.** Deux personnes editant le meme fichier
ne s'ecrasent pas : chacune publie sa version, et l'ecart se regle comme un
conflit ordinaire, avec les deux contenus conserves.
"""

from __future__ import annotations

import io
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import OperationInvalide

from .models import Brouillon, File, Folder, Kind, Origine, est_editable
from .services import creer_ou_mettre_a_jour_fichier, nom_disponible

#: Contenu initial d'un croquis vide : une feuille au format A4 paysage.
CROQUIS_VIDE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1123 794" '
    'width="1123" height="794">\n'
    '  <rect width="1123" height="794" fill="#ffffff"/>\n'
    "</svg>\n"
)


def verifier_editable(fichier: File) -> None:
    if not est_editable(fichier.name):
        raise OperationInvalide(
            "Ce format ne se modifie pas dans l'application. "
            "Téléversez une nouvelle version depuis votre poste."
        )


def lire_contenu(fichier: File) -> str:
    """Contenu textuel de la version courante."""
    from apps.common.object_storage import stockage

    verifier_editable(fichier)
    if not fichier.current_version_id:
        return ""
    if fichier.size_bytes > settings.EDITION_MAX_CARACTERES * 2:
        raise OperationInvalide(
            "Document trop volumineux pour être modifié dans l'application."
        )
    with stockage().lire(fichier.current_version.storage_key) as flux:
        return flux.read().decode("utf-8", errors="replace")


def brouillon_de(fichier: File, agent) -> Brouillon | None:
    return Brouillon.objects.filter(file=fichier, author=agent).first()


@transaction.atomic
def enregistrer_brouillon(fichier: File, agent, contenu: str) -> dict:
    """Sauvegarde automatique. Publie une version si l'attente a assez duré."""
    verifier_editable(fichier)
    if len(contenu) > settings.EDITION_MAX_CARACTERES:
        raise OperationInvalide(
            f"Document trop long (maximum {settings.EDITION_MAX_CARACTERES} caractères)."
        )

    version_courante = (
        fichier.current_version.version_number if fichier.current_version_id else 0
    )
    brouillon, _ = Brouillon.objects.update_or_create(
        file=fichier,
        author=agent,
        defaults={"contenu": contenu, "base_version": version_courante},
    )

    # Une version de sécurité, à intervalle régulier, pour qu'une coupure ne
    # coûte jamais plus que cet intervalle.
    limite = timezone.now() - timezone.timedelta(
        minutes=settings.EDITION_INTERVALLE_VERSION_MINUTES
    )
    reference = (
        fichier.current_version.created_at
        if fichier.current_version_id
        else fichier.created_at
    )
    if reference < limite and contenu.strip():
        version = publier_brouillon(
            fichier, agent, commentaire="Sauvegarde automatique", conserver=True
        )
        return {
            "enregistre_le": timezone.now(),
            "version_publiee": version.version_number,
            "taille": brouillon.taille_octets,
        }

    return {
        "enregistre_le": brouillon.derniere_frappe,
        "version_publiee": None,
        "taille": brouillon.taille_octets,
    }


@transaction.atomic
def publier_brouillon(
    fichier: File, agent, commentaire: str = "", conserver: bool = False
):
    """Transforme le brouillon en version. C'est le seul chemin vers l'historique."""
    brouillon = brouillon_de(fichier, agent)
    if brouillon is None:
        raise OperationInvalide("Aucune modification en attente.")

    _, version = creer_ou_mettre_a_jour_fichier(
        nom=fichier.name,
        dossier=fichier.folder,
        contenu=io.BytesIO(brouillon.contenu.encode("utf-8")),
        auteur=agent,
        commentaire=commentaire or "Modifié dans l'application",
        origine=Origine.WEB,
        fichier_existant=fichier,
    )
    if conserver:
        brouillon.publie_le = timezone.now()
        brouillon.save(update_fields=["publie_le", "updated_at"])
    else:
        brouillon.delete()
    return version


def abandonner_brouillon(fichier: File, agent) -> None:
    Brouillon.objects.filter(file=fichier, author=agent).delete()


@transaction.atomic
def creer_document(
    *, nom: str, dossier: Folder, auteur, contenu: str = "", croquis: bool = False
) -> File:
    """Cree un document vide, modifiable immediatement dans l'application."""
    if croquis:
        if not nom.lower().endswith(".svg"):
            nom = f"{nom}.svg"
        contenu = contenu or CROQUIS_VIDE
    elif not Path(nom).suffix:
        nom = f"{nom}.md"

    if not est_editable(nom):
        raise OperationInvalide(
            "Extension non modifiable dans l'application "
            "(.md, .txt, .csv, .json, .geojson, .svg)."
        )

    nom = nom_disponible(nom, dossier=dossier, modele=File)
    fichier, _ = creer_ou_mettre_a_jour_fichier(
        nom=nom,
        dossier=dossier,
        contenu=io.BytesIO(contenu.encode("utf-8")),
        auteur=auteur,
        commentaire="Création dans l'application",
    )
    if croquis:
        File.objects.filter(pk=fichier.pk).update(kind=Kind.CROQUIS)
        fichier.refresh_from_db()
    return fichier
