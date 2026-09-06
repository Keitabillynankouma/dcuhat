"""Recherche, partage, journal d'activite et authentification."""

import io

from django.utils import timezone

from apps.audit.models import ActivityLog
from apps.sharing.models import Niveau, Permission, ShareLink
from apps.storage import services

from .base import BaseDCUHATTest


class TestRecherche(BaseDCUHATTest):
    def setUp(self):
        super().setUp()
        from apps.geo.tasks import indexer_texte

        self.plan, _ = services.creer_ou_mettre_a_jour_fichier(
            nom="permis-construire-2026-014.txt", dossier=self.leves,
            contenu=io.BytesIO("Permis de construire quartier Centre".encode()),
            auteur=self.agent_cadastre,
        )
        indexer_texte(self.plan)
        self.autre, _ = services.creer_ou_mettre_a_jour_fichier(
            nom="reunion.txt", dossier=self.racine_urbanisme,
            contenu=io.BytesIO("compte rendu".encode()), auteur=self.agent_urbanisme,
        )
        indexer_texte(self.autre)

    def test_recherche_par_nom(self):
        client = self.client_pour(self.agent_cadastre)
        donnees = client.get("/api/v1/search/?q=permis").json()
        noms = [f["name"] for f in donnees["fichiers"]]
        self.assertIn(self.plan.name, noms)

    def test_recherche_dans_le_contenu_extrait(self):
        client = self.client_pour(self.agent_cadastre)
        donnees = client.get("/api/v1/search/?q=quartier").json()
        self.assertGreaterEqual(donnees["total_fichiers"], 1)

    def test_la_recherche_ne_traverse_pas_les_services(self):
        client = self.client_pour(self.agent_cadastre)
        donnees = client.get("/api/v1/search/?q=compte").json()
        noms = [f["name"] for f in donnees["fichiers"]]
        self.assertNotIn(self.autre.name, noms)

    def test_filtre_par_type(self):
        client = self.client_pour(self.agent_cadastre)
        donnees = client.get("/api/v1/search/?kind=VECTEUR").json()
        self.assertEqual(donnees["total_fichiers"], 0)

    def test_recherche_par_champ_metier(self):
        from apps.storage.models import FileMetadata

        FileMetadata.objects.create(
            file=self.plan, key="numero_parcelle", value="LB-2026-014"
        )
        client = self.client_pour(self.agent_cadastre)
        donnees = client.get("/api/v1/search/?meta_numero_parcelle=LB-2026").json()
        self.assertEqual(donnees["total_fichiers"], 1)


class TestPartage(BaseDCUHATTest):
    def test_lien_public_donne_acces_sans_compte(self):
        fichier, _ = services.creer_ou_mettre_a_jour_fichier(
            nom="arrete.txt", dossier=self.leves, contenu=self.contenu(),
            auteur=self.chef_cadastre,
        )
        client = self.client_pour(self.chef_cadastre)
        cree = client.post(
            "/api/v1/share-links/",
            {"file": str(fichier.id), "level": "READ"}, format="json",
        )
        self.assertEqual(cree.status_code, 201)
        token = cree.json()["token"]

        from rest_framework.test import APIClient

        anonyme = APIClient()
        reponse = anonyme.post(f"/api/v1/share-links/{token}/access/", {}, format="json")
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.json()["fichier"]["name"], "arrete.txt")

    def test_lien_expire_est_refuse(self):
        fichier, _ = services.creer_ou_mettre_a_jour_fichier(
            nom="arrete.txt", dossier=self.leves, contenu=self.contenu(),
            auteur=self.chef_cadastre,
        )
        lien = ShareLink.objects.create(
            file=fichier, created_by=self.chef_cadastre,
            expires_at=timezone.now() - timezone.timedelta(days=1),
        )
        from rest_framework.test import APIClient

        reponse = APIClient().post(f"/api/v1/share-links/{lien.token}/access/", {}, format="json")
        self.assertEqual(reponse.status_code, 410)
        self.assertEqual(reponse.json()["code"], "SHARE_LINK_EXPIRED")

    def test_lien_protege_par_mot_de_passe(self):
        fichier, _ = services.creer_ou_mettre_a_jour_fichier(
            nom="arrete.txt", dossier=self.leves, contenu=self.contenu(),
            auteur=self.chef_cadastre,
        )
        client = self.client_pour(self.chef_cadastre)
        token = client.post(
            "/api/v1/share-links/",
            {"file": str(fichier.id), "mot_de_passe": "secret-lambayin"},
            format="json",
        ).json()["token"]

        from rest_framework.test import APIClient

        anonyme = APIClient()
        self.assertEqual(
            anonyme.post(f"/api/v1/share-links/{token}/access/", {}, format="json").status_code,
            400,
        )
        self.assertEqual(
            anonyme.post(
                f"/api/v1/share-links/{token}/access/",
                {"mot_de_passe": "secret-lambayin"}, format="json",
            ).status_code,
            200,
        )

    def test_un_agent_sans_droit_de_gestion_ne_peut_pas_partager(self):
        Permission.objects.create(
            folder=self.leves, grantee_user=self.agent_urbanisme, level=Niveau.READ,
            granted_by=self.chef_cadastre,
        )
        client = self.client_pour(self.agent_urbanisme)
        reponse = client.post(
            "/api/v1/permissions/",
            {
                "folder": str(self.leves.id),
                "grantee_user": str(self.directeur.id),
                "level": "WRITE",
            },
            format="json",
        )
        self.assertEqual(reponse.status_code, 403)


class TestJournal(BaseDCUHATTest):
    def test_chaque_action_laisse_une_trace_attribuee(self):
        client = self.client_pour(self.agent_cadastre)
        client.post(
            "/api/v1/files/upload/simple/",
            {"dossier": str(self.leves.id), "fichier": io.BytesIO(b"leve")},
            format="multipart",
        )
        entree = ActivityLog.objects.filter(action="FILE_UPLOAD").first()
        self.assertIsNotNone(entree)
        self.assertEqual(entree.actor_id, self.agent_cadastre.id)
        self.assertTrue(entree.target_path.startswith("/cadastre/"))

    def test_un_agent_ne_voit_que_son_propre_journal(self):
        services.creer_dossier(nom="X", parent=self.leves, auteur=self.chef_cadastre)
        client = self.client_pour(self.agent_cadastre)
        donnees = client.get("/api/v1/activity/").json()
        acteurs = {e["actor"] for e in donnees["results"]}
        self.assertTrue(acteurs <= {str(self.agent_cadastre.id)})

    def test_le_journal_n_expose_aucune_route_d_ecriture(self):
        client = self.client_pour(self.admin)
        reponse = client.post("/api/v1/activity/", {"action": "LOGIN"}, format="json")
        self.assertEqual(reponse.status_code, 405)

    def test_export_csv_du_journal(self):
        client = self.client_pour(self.admin)
        reponse = client.get("/api/v1/activity/export/")
        self.assertEqual(reponse.status_code, 200)
        self.assertIn("text/csv", reponse["Content-Type"])


class TestAuthentification(BaseDCUHATTest):
    def test_connexion_retourne_un_jeton(self):
        from rest_framework.test import APIClient

        reponse = APIClient().post(
            "/api/v1/auth/login/",
            {"email": "agent.cadastre@dcuhat.test", "password": "MotDePasseSolide2026"},
            format="json",
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertIn("access", reponse.json())

    def test_verrouillage_apres_echecs_repetes(self):
        from django.test import override_settings
        from rest_framework.test import APIClient

        client = APIClient()
        with override_settings(LOGIN_MAX_FAILED_ATTEMPTS=3):
            for _ in range(3):
                client.post(
                    "/api/v1/auth/login/",
                    {"email": "agent.cadastre@dcuhat.test", "password": "faux"},
                    format="json",
                )
            reponse = client.post(
                "/api/v1/auth/login/",
                {"email": "agent.cadastre@dcuhat.test", "password": "MotDePasseSolide2026"},
                format="json",
            )
        self.assertEqual(reponse.status_code, 423)
        self.assertEqual(reponse.json()["code"], "ACCOUNT_LOCKED")

    def test_les_echecs_sont_journalises(self):
        from rest_framework.test import APIClient

        APIClient().post(
            "/api/v1/auth/login/",
            {"email": "agent.cadastre@dcuhat.test", "password": "faux"},
            format="json",
        )
        self.assertTrue(ActivityLog.objects.filter(action="LOGIN_FAILED").exists())

    def test_api_inaccessible_sans_jeton(self):
        from rest_framework.test import APIClient

        self.assertEqual(APIClient().get("/api/v1/folders/").status_code, 401)

    def test_seul_un_administrateur_cree_des_comptes(self):
        client = self.client_pour(self.chef_cadastre)
        reponse = client.post(
            "/api/v1/auth/users/",
            {"email": "nouveau@dcuhat.test", "role": "AGENT"}, format="json",
        )
        self.assertEqual(reponse.status_code, 403)
