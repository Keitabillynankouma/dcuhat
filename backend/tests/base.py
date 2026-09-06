from __future__ import annotations

import io
import shutil
import tempfile

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Role, Service, User
from apps.common import object_storage
from apps.storage.models import Folder


class BaseDCUHATTest(TestCase):
    """Socle commun : un stockage objet temporaire et une Direction miniature."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._racine_stockage = tempfile.mkdtemp(prefix="dcuhat-test-")
        object_storage._instance = object_storage.StockageLocal(cls._racine_stockage)

    @classmethod
    def tearDownClass(cls):
        object_storage.reinitialiser_stockage()
        shutil.rmtree(cls._racine_stockage, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.service_cadastre = Service.objects.create(
            name="Service du Cadastre", code="CADASTRE", quota_bytes=10 * 1024**2
        )
        self.service_urbanisme = Service.objects.create(
            name="Service de l'Urbanisme", code="URBANISME"
        )

        self.admin = User.objects.create_user(
            "admin@dcuhat.test", "MotDePasseSolide2026", role=Role.ADMIN,
            first_name="Awa", last_name="Camara",
        )
        self.chef_cadastre = User.objects.create_user(
            "chef.cadastre@dcuhat.test", "MotDePasseSolide2026",
            role=Role.CHEF_SERVICE, service=self.service_cadastre,
            first_name="Mamadou", last_name="Diallo",
        )
        self.agent_cadastre = User.objects.create_user(
            "agent.cadastre@dcuhat.test", "MotDePasseSolide2026",
            role=Role.AGENT, service=self.service_cadastre,
            first_name="Fatou", last_name="Bah",
        )
        self.agent_urbanisme = User.objects.create_user(
            "agent.urbanisme@dcuhat.test", "MotDePasseSolide2026",
            role=Role.AGENT, service=self.service_urbanisme,
            first_name="Ibrahima", last_name="Sow",
        )
        self.directeur = User.objects.create_user(
            "directeur@dcuhat.test", "MotDePasseSolide2026", role=Role.DIRECTEUR,
            first_name="Aissatou", last_name="Barry",
        )

        self.racine_cadastre = Folder.objects.create(
            name="Cadastre", owner=self.admin, service=self.service_cadastre,
            is_service_root=True,
        )
        self.leves = Folder.objects.create(
            name="Leves topographiques", parent=self.racine_cadastre,
            owner=self.chef_cadastre, service=self.service_cadastre,
        )
        self.racine_urbanisme = Folder.objects.create(
            name="Urbanisme", owner=self.admin, service=self.service_urbanisme,
            is_service_root=True,
        )

    # -- utilitaires -------------------------------------------------------
    def client_pour(self, utilisateur) -> APIClient:
        client = APIClient()
        client.force_authenticate(user=utilisateur)
        return client

    def contenu(self, texte: str = "leve topographique") -> io.BytesIO:
        return io.BytesIO(texte.encode("utf-8"))
