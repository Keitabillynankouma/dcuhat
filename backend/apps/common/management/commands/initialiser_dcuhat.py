"""Initialise la plateforme pour la Direction : services, arborescence de base,
compte administrateur.

    python manage.py initialiser_dcuhat --admin-email=... --admin-password=...
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Role, Service, User
from apps.storage.models import Folder

SERVICES = [
    ("Service de l'Urbanisme et de la Planification", "URBANISME"),
    ("Service de l'Habitat et du Logement", "HABITAT"),
    ("Service de l'Amenagement du Territoire", "AMENAGEMENT"),
    ("Service du Cadastre et de la Topographie", "CADASTRE"),
    ("Service des Affaires Domaniales", "DOMANIAL"),
    ("Secretariat et Archives", "ARCHIVES"),
]

#: Sous-dossiers crees dans chaque service, adaptes au travail de la Direction.
ARBORESCENCE = {
    "URBANISME": [
        "Permis de construire",
        "Certificats d'urbanisme",
        "Lotissements",
        "Plans d'urbanisme",
        "Contentieux",
    ],
    "HABITAT": ["Programmes de logement", "Enquetes habitat", "Salubrite"],
    "AMENAGEMENT": ["Schemas d'amenagement", "Voirie et reseaux", "Espaces publics"],
    "CADASTRE": [
        "Leves topographiques",
        "Plans cadastraux",
        "Bornage",
        "Donnees GPS terrain",
        "Orthophotos",
    ],
    "DOMANIAL": ["Titres fonciers", "Baux communaux", "Litiges fonciers"],
    "ARCHIVES": ["Arretes et deliberations", "Courriers", "Archives numerisees"],
}


class Command(BaseCommand):
    help = "Cree les services, l'arborescence de base et le compte administrateur."

    def add_arguments(self, parser):
        parser.add_argument("--admin-email", default="admin@dcuhat.lambayin.local")
        parser.add_argument("--admin-password", default="")
        parser.add_argument("--quota-go", type=int, default=50)

    @transaction.atomic
    def handle(self, *args, **options):
        email = options["admin_email"].lower()
        mot_de_passe = options["admin_password"]

        admin = User.objects.filter(email=email).first()
        if admin is None:
            if not mot_de_passe:
                from django.utils.crypto import get_random_string

                mot_de_passe = get_random_string(16)
                self.stdout.write(
                    self.style.WARNING(
                        f"Mot de passe administrateur genere : {mot_de_passe}"
                    )
                )
            admin = User.objects.create_superuser(
                email=email,
                password=mot_de_passe,
                first_name="Administrateur",
                last_name="DCUHAT",
                role=Role.ADMIN,
            )
            self.stdout.write(self.style.SUCCESS(f"Compte administrateur cree : {email}"))

        crees = 0
        for nom, code in SERVICES:
            service, nouveau = Service.objects.get_or_create(
                code=code,
                defaults={"name": nom, "quota_bytes": options["quota_go"] * 1024**3},
            )
            racine = Folder.objects.filter(
                is_service_root=True, service=service, is_deleted=False
            ).first()
            if racine is None:
                racine = Folder.objects.create(
                    name=nom, parent=None, owner=admin, service=service,
                    is_service_root=True,
                )
                service.root_folder = racine
                service.save(update_fields=["root_folder", "updated_at"])
            for sous_dossier in ARBORESCENCE.get(code, []):
                _, nouveau_dossier = Folder.objects.get_or_create(
                    parent=racine, name=sous_dossier, is_deleted=False,
                    defaults={"owner": admin, "service": service},
                )
                crees += int(nouveau_dossier)

        self.stdout.write(
            self.style.SUCCESS(
                f"{len(SERVICES)} services en place, {crees} dossiers metier crees."
            )
        )
        self.stdout.write(
            "Connectez-vous sur /admin/ ou via l'interface web pour creer les agents."
        )
