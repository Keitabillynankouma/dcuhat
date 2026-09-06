"""Panneau d'administration : gestion des agents, des services et des espaces.

Ces routes donnent les pleins pouvoirs sur la Direction : chaque test verifie
autant ce qu'elles permettent que ce qu'elles interdisent.
"""

from apps.accounts.models import Role, Service, User
from apps.storage.models import Folder

from .base import BaseDCUHATTest


class TestGestionDesAgents(BaseDCUHATTest):
    def test_admin_cree_un_agent_et_recoit_un_mot_de_passe_provisoire(self):
        client = self.client_pour(self.admin)
        reponse = client.post(
            "/api/v1/auth/users/",
            {
                "email": "m.sylla@dcuhat.test",
                "first_name": "Mariama",
                "last_name": "Sylla",
                "role": Role.AGENT,
                "service": str(self.service_cadastre.id),
                "fonction": "Technicienne topographe",
            },
            format="json",
        )
        self.assertEqual(reponse.status_code, 201)
        provisoire = reponse.json()["mot_de_passe_provisoire"]
        self.assertGreaterEqual(len(provisoire), 12)

        agent = User.objects.get(email="m.sylla@dcuhat.test")
        self.assertTrue(agent.check_password(provisoire))
        self.assertTrue(agent.must_change_password)
        self.assertEqual(agent.service, self.service_cadastre)

    def test_le_mot_de_passe_choisi_n_est_pas_renvoye(self):
        client = self.client_pour(self.admin)
        reponse = client.post(
            "/api/v1/auth/users/",
            {
                "email": "choisi@dcuhat.test",
                "role": Role.AGENT,
                "password": "MotDePasseSolide2026",
            },
            format="json",
        )
        self.assertEqual(reponse.status_code, 201)
        self.assertEqual(reponse.json()["mot_de_passe_provisoire"], "")

    def test_adresse_deja_utilisee_refusee(self):
        client = self.client_pour(self.admin)
        reponse = client.post(
            "/api/v1/auth/users/",
            {"email": self.agent_cadastre.email, "role": Role.AGENT},
            format="json",
        )
        self.assertEqual(reponse.status_code, 400)

    def test_changement_de_role(self):
        client = self.client_pour(self.admin)
        reponse = client.post(
            f"/api/v1/auth/users/{self.agent_cadastre.id}/role/",
            {"role": Role.CHEF_SERVICE},
            format="json",
        )
        self.assertEqual(reponse.status_code, 200)
        self.agent_cadastre.refresh_from_db()
        self.assertEqual(self.agent_cadastre.role, Role.CHEF_SERVICE)

    def test_le_changement_de_role_est_journalise(self):
        from apps.audit.models import ActivityLog

        client = self.client_pour(self.admin)
        client.post(
            f"/api/v1/auth/users/{self.agent_cadastre.id}/role/",
            {"role": Role.LECTEUR},
            format="json",
        )
        entree = ActivityLog.objects.filter(action="ROLE_CHANGE").first()
        self.assertIsNotNone(entree)
        self.assertEqual(entree.metadata["nouveau"], Role.LECTEUR)

    def test_role_inconnu_refuse(self):
        client = self.client_pour(self.admin)
        reponse = client.post(
            f"/api/v1/auth/users/{self.agent_cadastre.id}/role/",
            {"role": "SUPER_CHEF"},
            format="json",
        )
        self.assertEqual(reponse.status_code, 400)

    def test_un_admin_ne_peut_pas_se_retirer_ses_propres_droits(self):
        """Se retirer le dernier acces administrateur bloquerait la plateforme."""
        client = self.client_pour(self.admin)
        reponse = client.post(
            f"/api/v1/auth/users/{self.admin.id}/role/",
            {"role": Role.AGENT},
            format="json",
        )
        self.assertEqual(reponse.status_code, 400)

    def test_desactivation_puis_reactivation(self):
        client = self.client_pour(self.admin)
        self.assertEqual(
            client.delete(f"/api/v1/auth/users/{self.agent_cadastre.id}/").status_code, 204
        )
        self.agent_cadastre.refresh_from_db()
        self.assertFalse(self.agent_cadastre.is_active)
        self.assertTrue(User.objects.filter(pk=self.agent_cadastre.pk).exists())

        client.post(f"/api/v1/auth/users/{self.agent_cadastre.id}/activer/")
        self.agent_cadastre.refresh_from_db()
        self.assertTrue(self.agent_cadastre.is_active)

    def test_un_admin_ne_peut_pas_se_desactiver(self):
        client = self.client_pour(self.admin)
        reponse = client.delete(f"/api/v1/auth/users/{self.admin.id}/")
        self.assertEqual(reponse.status_code, 400)

    def test_reinitialisation_du_mot_de_passe(self):
        client = self.client_pour(self.admin)
        reponse = client.post(
            f"/api/v1/auth/users/{self.agent_cadastre.id}/reinitialiser-mot-de-passe/"
        )
        self.assertEqual(reponse.status_code, 200)
        nouveau = reponse.json()["mot_de_passe_provisoire"]
        self.agent_cadastre.refresh_from_db()
        self.assertTrue(self.agent_cadastre.check_password(nouveau))
        self.assertTrue(self.agent_cadastre.must_change_password)

    def test_recherche_et_filtres(self):
        client = self.client_pour(self.admin)
        parNom = client.get("/api/v1/auth/users/?q=Diallo").json()["results"]
        self.assertEqual(len(parNom), 1)
        parRole = client.get(f"/api/v1/auth/users/?role={Role.AGENT}").json()["results"]
        self.assertEqual(len(parRole), 2)

    def test_un_agent_ne_peut_rien_administrer(self):
        client = self.client_pour(self.agent_cadastre)
        self.assertEqual(client.get("/api/v1/auth/users/").status_code, 403)
        self.assertEqual(
            client.post("/api/v1/auth/users/", {"email": "x@y.z"}, format="json").status_code,
            403,
        )
        self.assertEqual(client.get("/api/v1/auth/statistiques/").status_code, 403)


class TestGestionDesServices(BaseDCUHATTest):
    def test_creation_d_un_service(self):
        client = self.client_pour(self.admin)
        reponse = client.post(
            "/api/v1/auth/services/",
            {"name": "Service des Espaces Verts", "code": "ESPACES_VERTS"},
            format="json",
        )
        self.assertEqual(reponse.status_code, 201)
        self.assertTrue(Service.objects.filter(code="ESPACES_VERTS").exists())

    def test_le_service_expose_son_usage_et_ses_effectifs(self):
        from apps.storage import services as storage_services

        storage_services.creer_ou_mettre_a_jour_fichier(
            nom="leve.txt", dossier=self.leves, contenu=self.contenu("mesures"),
            auteur=self.agent_cadastre,
        )
        client = self.client_pour(self.admin)
        donnees = client.get(f"/api/v1/auth/services/{self.service_cadastre.id}/").json()
        self.assertGreater(donnees["usage_octets"], 0)
        self.assertEqual(donnees["nombre_agents"], 2)

    def test_un_agent_consulte_les_services_mais_n_en_cree_pas(self):
        client = self.client_pour(self.agent_cadastre)
        self.assertEqual(client.get("/api/v1/auth/services/").status_code, 200)
        self.assertEqual(
            client.post(
                "/api/v1/auth/services/", {"name": "X", "code": "X"}, format="json"
            ).status_code,
            403,
        )


class TestCreationDEspaces(BaseDCUHATTest):
    def test_admin_cree_un_espace_racine_rattache_a_un_service(self):
        client = self.client_pour(self.admin)
        service = Service.objects.create(name="Espaces Verts", code="EV")
        reponse = client.post(
            "/api/v1/folders/",
            {"name": "Espaces Verts", "service": str(service.id)},
            format="json",
        )
        self.assertEqual(reponse.status_code, 201)
        dossier = Folder.objects.get(pk=reponse.json()["id"])
        self.assertIsNone(dossier.parent)
        self.assertTrue(dossier.is_service_root)
        service.refresh_from_db()
        self.assertEqual(service.root_folder_id, dossier.id)

    def test_un_agent_ne_cree_pas_d_espace_racine(self):
        client = self.client_pour(self.agent_cadastre)
        reponse = client.post("/api/v1/folders/", {"name": "Mon espace"}, format="json")
        self.assertEqual(reponse.status_code, 403)
        self.assertEqual(reponse.json()["code"], "PERMISSION_DENIED")

    def test_un_agent_cree_un_sous_dossier_dans_son_service(self):
        client = self.client_pour(self.agent_cadastre)
        reponse = client.post(
            "/api/v1/folders/",
            {"name": "Campagne mars 2026", "parent": str(self.leves.id)},
            format="json",
        )
        self.assertEqual(reponse.status_code, 201)
        self.assertEqual(reponse.json()["parent"], str(self.leves.id))

    def test_creation_refusee_dans_un_dossier_non_autorise(self):
        client = self.client_pour(self.agent_urbanisme)
        reponse = client.post(
            "/api/v1/folders/",
            {"name": "Intrusion", "parent": str(self.leves.id)},
            format="json",
        )
        self.assertEqual(reponse.status_code, 404)


class TestStatistiques(BaseDCUHATTest):
    def test_le_tableau_de_bord_donne_les_chiffres_de_tete(self):
        from apps.storage import services as storage_services

        storage_services.creer_ou_mettre_a_jour_fichier(
            nom="plan.txt", dossier=self.leves, contenu=self.contenu(),
            auteur=self.agent_cadastre,
        )
        client = self.client_pour(self.admin)
        donnees = client.get("/api/v1/auth/statistiques/").json()
        self.assertEqual(donnees["agents"]["total"], 5)
        self.assertEqual(donnees["services"], 2)
        self.assertEqual(donnees["fichiers"]["total"], 1)
        self.assertGreater(donnees["stockage_octets"], 0)
        self.assertEqual(donnees["conflits_ouverts"], 0)


class TestSuppressionDEspace(BaseDCUHATTest):
    def test_un_espace_part_a_la_corbeille_avec_son_contenu(self):
        from apps.storage import services as storage_services

        fichier, _ = storage_services.creer_ou_mettre_a_jour_fichier(
            nom="leve.txt", dossier=self.leves, contenu=self.contenu(),
            auteur=self.agent_cadastre,
        )
        client = self.client_pour(self.admin)
        reponse = client.delete(f"/api/v1/folders/{self.racine_cadastre.id}/")
        self.assertEqual(reponse.status_code, 204)

        self.racine_cadastre.refresh_from_db()
        self.leves.refresh_from_db()
        fichier.refresh_from_db()
        self.assertTrue(self.racine_cadastre.is_deleted)
        self.assertTrue(self.leves.is_deleted)
        self.assertTrue(fichier.is_deleted)

    def test_un_espace_supprime_est_restaurable(self):
        client = self.client_pour(self.admin)
        client.delete(f"/api/v1/folders/{self.racine_cadastre.id}/")
        reponse = client.post(f"/api/v1/trash/{self.racine_cadastre.id}/")
        self.assertEqual(reponse.status_code, 200)
        self.racine_cadastre.refresh_from_db()
        self.leves.refresh_from_db()
        self.assertFalse(self.racine_cadastre.is_deleted)
        self.assertFalse(self.leves.is_deleted)

    def test_la_purge_libere_les_objets_binaires(self):
        from apps.common.object_storage import stockage
        from apps.storage import services as storage_services
        from apps.storage.models import File, FileVersion

        fichier, version = storage_services.creer_ou_mettre_a_jour_fichier(
            nom="leve.txt", dossier=self.leves, contenu=self.contenu("a effacer"),
            auteur=self.agent_cadastre,
        )
        cle = version.storage_key
        self.assertTrue(stockage().existe(cle))

        client = self.client_pour(self.admin)
        client.delete(f"/api/v1/folders/{self.racine_cadastre.id}/")
        reponse = client.delete(f"/api/v1/trash/{self.racine_cadastre.id}/")

        self.assertEqual(reponse.status_code, 204)
        self.assertFalse(File.objects.filter(pk=fichier.pk).exists())
        self.assertFalse(FileVersion.objects.filter(storage_key=cle).exists())
        self.assertFalse(stockage().existe(cle))

    def test_seul_un_admin_purge_definitivement(self):
        client_admin = self.client_pour(self.admin)
        client_admin.delete(f"/api/v1/folders/{self.leves.id}/")
        client = self.client_pour(self.chef_cadastre)
        reponse = client.delete(f"/api/v1/trash/{self.leves.id}/")
        self.assertEqual(reponse.status_code, 400)


class TestMotDePasse(BaseDCUHATTest):
    def test_un_agent_change_son_mot_de_passe(self):
        client = self.client_pour(self.agent_cadastre)
        reponse = client.post(
            "/api/v1/auth/password/change/",
            {"ancien": "MotDePasseSolide2026", "nouveau": "NouveauMotDePasse2027"},
            format="json",
        )
        self.assertEqual(reponse.status_code, 200)
        self.agent_cadastre.refresh_from_db()
        self.assertTrue(self.agent_cadastre.check_password("NouveauMotDePasse2027"))
        self.assertFalse(self.agent_cadastre.must_change_password)

    def test_l_ancien_mot_de_passe_est_exige(self):
        client = self.client_pour(self.agent_cadastre)
        reponse = client.post(
            "/api/v1/auth/password/change/",
            {"ancien": "faux", "nouveau": "NouveauMotDePasse2027"},
            format="json",
        )
        self.assertEqual(reponse.status_code, 400)
        self.agent_cadastre.refresh_from_db()
        self.assertTrue(self.agent_cadastre.check_password("MotDePasseSolide2026"))

    def test_un_mot_de_passe_trop_faible_est_refuse(self):
        client = self.client_pour(self.agent_cadastre)
        reponse = client.post(
            "/api/v1/auth/password/change/",
            {"ancien": "MotDePasseSolide2026", "nouveau": "motdepasse"},
            format="json",
        )
        self.assertEqual(reponse.status_code, 400)

    def test_un_agent_modifie_son_profil_mais_pas_son_role(self):
        client = self.client_pour(self.agent_cadastre)
        reponse = client.patch(
            "/api/v1/auth/me/",
            {"first_name": "Fatoumata", "fonction": "Geometre", "role": "ADMIN"},
            format="json",
        )
        self.assertEqual(reponse.status_code, 200)
        self.agent_cadastre.refresh_from_db()
        self.assertEqual(self.agent_cadastre.first_name, "Fatoumata")
        self.assertEqual(self.agent_cadastre.role, "AGENT")
