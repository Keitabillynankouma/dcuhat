"""Le moteur de permissions est le coeur de la confidentialite de la
plateforme : chaque regle de la specification 6.3 a son test."""

from apps.sharing.models import Niveau, Permission
from apps.sharing.services import (
    dossiers_visibles,
    niveau_sur_dossier,
    niveau_sur_fichier,
    peut,
)
from apps.storage.models import Folder

from .base import BaseDCUHATTest


class TestMoteurPermissions(BaseDCUHATTest):
    def test_admin_gere_tout(self):
        self.assertEqual(
            niveau_sur_dossier(self.admin, self.racine_urbanisme), Niveau.MANAGE
        )

    def test_chef_de_service_gere_son_service(self):
        self.assertEqual(
            niveau_sur_dossier(self.chef_cadastre, self.leves), Niveau.MANAGE
        )

    def test_agent_ecrit_dans_son_service(self):
        self.assertEqual(
            niveau_sur_dossier(self.agent_cadastre, self.leves), Niveau.WRITE
        )

    def test_agent_ne_voit_pas_un_autre_service(self):
        self.assertIsNone(
            niveau_sur_dossier(self.agent_cadastre, self.racine_urbanisme)
        )

    def test_directeur_lit_tout_mais_n_ecrit_pas(self):
        self.assertEqual(niveau_sur_dossier(self.directeur, self.leves), Niveau.READ)
        self.assertFalse(peut(self.directeur, self.leves, Niveau.WRITE))

    def test_permission_explicite_traverse_les_services(self):
        Permission.objects.create(
            folder=self.leves, grantee_user=self.agent_urbanisme,
            level=Niveau.READ, granted_by=self.chef_cadastre,
        )
        self.assertEqual(
            niveau_sur_dossier(self.agent_urbanisme, self.leves), Niveau.READ
        )

    def test_permission_heritee_par_le_sous_arbre(self):
        sous_dossier = Folder.objects.create(
            name="Campagne 2026", parent=self.leves, owner=self.chef_cadastre,
            service=self.service_cadastre,
        )
        Permission.objects.create(
            folder=self.leves, grantee_user=self.agent_urbanisme,
            level=Niveau.WRITE, inherit=True, granted_by=self.chef_cadastre,
        )
        self.assertEqual(
            niveau_sur_dossier(self.agent_urbanisme, sous_dossier), Niveau.WRITE
        )

    def test_permission_non_heritee_reste_locale(self):
        sous_dossier = Folder.objects.create(
            name="Confidentiel", parent=self.leves, owner=self.chef_cadastre,
            service=self.service_cadastre,
        )
        Permission.objects.create(
            folder=self.leves, grantee_user=self.agent_urbanisme,
            level=Niveau.READ, inherit=False, granted_by=self.chef_cadastre,
        )
        self.assertEqual(
            niveau_sur_dossier(self.agent_urbanisme, self.leves), Niveau.READ
        )
        self.assertIsNone(niveau_sur_dossier(self.agent_urbanisme, sous_dossier))

    def test_le_niveau_le_plus_eleve_l_emporte(self):
        Permission.objects.create(
            folder=self.leves, grantee_user=self.agent_urbanisme,
            level=Niveau.READ, granted_by=self.chef_cadastre,
        )
        Permission.objects.create(
            folder=self.leves, grantee_service=self.service_urbanisme,
            level=Niveau.WRITE, granted_by=self.chef_cadastre,
        )
        self.assertEqual(
            niveau_sur_dossier(self.agent_urbanisme, self.leves), Niveau.WRITE
        )

    def test_permission_expiree_ne_donne_plus_acces(self):
        from django.utils import timezone

        Permission.objects.create(
            folder=self.leves, grantee_user=self.agent_urbanisme, level=Niveau.READ,
            granted_by=self.chef_cadastre,
            expires_at=timezone.now() - timezone.timedelta(hours=1),
        )
        self.assertIsNone(niveau_sur_dossier(self.agent_urbanisme, self.leves))

    def test_liste_visible_ne_fuit_pas_les_autres_services(self):
        chemins = set(dossiers_visibles(self.agent_cadastre).values_list("path", flat=True))
        self.assertIn(self.leves.path, chemins)
        self.assertNotIn(self.racine_urbanisme.path, chemins)


class TestAccesAPI(BaseDCUHATTest):
    def test_dossier_non_autorise_repond_404_et_non_403(self):
        """Repondre 403 revelerait l'existence du dossier."""
        client = self.client_pour(self.agent_cadastre)
        reponse = client.get(f"/api/v1/folders/{self.racine_urbanisme.id}/")
        self.assertEqual(reponse.status_code, 404)

    def test_lecture_seule_refusee_en_ecriture(self):
        from apps.sharing.models import Permission

        Permission.objects.create(
            folder=self.leves, grantee_user=self.agent_urbanisme,
            level=Niveau.READ, granted_by=self.chef_cadastre,
        )
        client = self.client_pour(self.agent_urbanisme)
        reponse = client.patch(
            f"/api/v1/folders/{self.leves.id}/", {"name": "Renomme"}, format="json"
        )
        self.assertEqual(reponse.status_code, 403)
        self.assertEqual(reponse.json()["code"], "PERMISSION_DENIED")
