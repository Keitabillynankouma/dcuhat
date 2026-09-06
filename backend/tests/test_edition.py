"""Édition dans l'application, brouillons et sauvegarde automatique.

La question centrale de ces tests : la sauvegarde automatique protège-t-elle
le travail de l'agent **sans** noyer l'historique sous des versions ?
"""

from django.test import override_settings
from django.utils import timezone

from apps.storage import edition
from apps.storage.models import Brouillon, File, Kind

from .base import BaseDCUHATTest


class TestBrouillons(BaseDCUHATTest):
    def setUp(self):
        super().setUp()
        self.note = edition.creer_document(
            nom="compte-rendu.md",
            dossier=self.leves,
            auteur=self.agent_cadastre,
            contenu="# Réunion du 12 mars\n",
        )

    def test_creation_d_un_document_vide(self):
        self.assertEqual(self.note.name, "compte-rendu.md")
        self.assertEqual(self.note.versions.count(), 1)
        self.assertIn("Réunion", edition.lire_contenu(self.note))

    def test_la_sauvegarde_automatique_ne_cree_pas_de_version(self):
        for texte in ("# Réunion", "# Réunion du", "# Réunion du 12 mars"):
            edition.enregistrer_brouillon(self.note, self.agent_cadastre, texte)
        self.note.refresh_from_db()
        self.assertEqual(self.note.versions.count(), 1)
        self.assertEqual(Brouillon.objects.filter(file=self.note).count(), 1)

    def test_publier_cree_une_version_et_efface_le_brouillon(self):
        edition.enregistrer_brouillon(
            self.note, self.agent_cadastre, "# Réunion\n\nPoints abordés."
        )
        version = edition.publier_brouillon(
            self.note, self.agent_cadastre, commentaire="Compte rendu validé"
        )
        self.note.refresh_from_db()
        self.assertEqual(version.version_number, 2)
        self.assertIn("Points abordés", edition.lire_contenu(self.note))
        self.assertFalse(Brouillon.objects.filter(file=self.note).exists())

    def test_le_brouillon_est_repris_a_la_reouverture(self):
        edition.enregistrer_brouillon(self.note, self.agent_cadastre, "travail en cours")
        client = self.client_pour(self.agent_cadastre)
        donnees = client.get(f"/api/v1/files/{self.note.id}/contenu/").json()
        self.assertEqual(donnees["brouillon"]["contenu"], "travail en cours")
        self.assertIn("Réunion", donnees["contenu"])

    def test_abandonner_revient_a_la_version_publiee(self):
        edition.enregistrer_brouillon(self.note, self.agent_cadastre, "à jeter")
        client = self.client_pour(self.agent_cadastre)
        reponse = client.delete(f"/api/v1/files/{self.note.id}/brouillon/")
        self.assertEqual(reponse.status_code, 204)
        self.assertIn("Réunion", edition.lire_contenu(self.note))

    @override_settings(EDITION_INTERVALLE_VERSION_MINUTES=0)
    def test_une_version_de_securite_est_publiee_apres_un_long_travail(self):
        """Une coupure ne doit jamais coûter plus que l'intervalle configuré."""
        resultat = edition.enregistrer_brouillon(
            self.note, self.agent_cadastre, "beaucoup de travail"
        )
        self.note.refresh_from_db()
        self.assertEqual(resultat["version_publiee"], 2)
        self.assertEqual(self.note.versions.count(), 2)
        self.assertIn("beaucoup de travail", edition.lire_contenu(self.note))

    def test_deux_agents_ont_chacun_leur_brouillon(self):
        edition.enregistrer_brouillon(self.note, self.agent_cadastre, "version terrain")
        edition.enregistrer_brouillon(self.note, self.chef_cadastre, "version bureau")
        self.assertEqual(Brouillon.objects.filter(file=self.note).count(), 2)
        self.assertEqual(
            edition.brouillon_de(self.note, self.agent_cadastre).contenu, "version terrain"
        )
        self.assertEqual(
            edition.brouillon_de(self.note, self.chef_cadastre).contenu, "version bureau"
        )

    def test_les_deux_publications_donnent_deux_versions_conservees(self):
        edition.enregistrer_brouillon(self.note, self.agent_cadastre, "version terrain")
        edition.enregistrer_brouillon(self.note, self.chef_cadastre, "version bureau")
        edition.publier_brouillon(self.note, self.agent_cadastre)
        edition.publier_brouillon(self.note, self.chef_cadastre)
        self.note.refresh_from_db()
        self.assertEqual(self.note.versions.count(), 3)
        self.assertEqual(edition.lire_contenu(self.note), "version bureau")

    def test_un_format_non_editable_est_refuse(self):
        from apps.common.exceptions import OperationInvalide
        from apps.storage import services

        binaire, _ = services.creer_ou_mettre_a_jour_fichier(
            nom="plan.pdf", dossier=self.leves, contenu=self.contenu("%PDF-1.4"),
            auteur=self.agent_cadastre,
        )
        with self.assertRaises(OperationInvalide):
            edition.lire_contenu(binaire)

    def test_un_lecteur_ne_peut_pas_enregistrer(self):
        from apps.sharing.models import Niveau, Permission

        Permission.objects.create(
            folder=self.leves, grantee_user=self.agent_urbanisme,
            level=Niveau.READ, granted_by=self.chef_cadastre,
        )
        client = self.client_pour(self.agent_urbanisme)
        reponse = client.put(
            f"/api/v1/files/{self.note.id}/brouillon/",
            {"contenu": "intrusion"}, format="json",
        )
        self.assertEqual(reponse.status_code, 403)

    @override_settings(EDITION_MAX_CARACTERES=50)
    def test_document_trop_long_refuse(self):
        client = self.client_pour(self.agent_cadastre)
        reponse = client.put(
            f"/api/v1/files/{self.note.id}/brouillon/",
            {"contenu": "x" * 100}, format="json",
        )
        self.assertEqual(reponse.status_code, 400)


class TestCroquis(BaseDCUHATTest):
    def test_creation_d_un_croquis_vide(self):
        croquis = edition.creer_document(
            nom="Croquis parcelle 14",
            dossier=self.leves,
            auteur=self.agent_cadastre,
            croquis=True,
        )
        self.assertTrue(croquis.name.endswith(".svg"))
        self.assertEqual(croquis.kind, Kind.CROQUIS)
        self.assertIn("<svg", edition.lire_contenu(croquis))

    def test_un_croquis_se_modifie_et_se_versionne(self):
        croquis = edition.creer_document(
            nom="croquis.svg", dossier=self.leves, auteur=self.agent_cadastre,
            croquis=True,
        )
        trace = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1123 794">'
            '<path d="M10 10 L100 100" stroke="#000" fill="none"/></svg>'
        )
        edition.enregistrer_brouillon(croquis, self.agent_cadastre, trace)
        edition.publier_brouillon(croquis, self.agent_cadastre, commentaire="Levé du 12")
        croquis.refresh_from_db()
        self.assertEqual(croquis.versions.count(), 2)
        self.assertIn("M10 10 L100 100", edition.lire_contenu(croquis))

    def test_creation_par_l_api(self):
        client = self.client_pour(self.agent_cadastre)
        reponse = client.post(
            "/api/v1/files/nouveau/",
            {"nom": "Croquis secteur 3", "dossier": str(self.leves.id), "croquis": True},
            format="json",
        )
        self.assertEqual(reponse.status_code, 201)
        self.assertEqual(reponse.json()["kind"], Kind.CROQUIS)
        self.assertTrue(File.objects.filter(name="Croquis secteur 3.svg").exists())

    def test_creation_refusee_sans_droit_d_ecriture(self):
        client = self.client_pour(self.agent_urbanisme)
        reponse = client.post(
            "/api/v1/files/nouveau/",
            {"nom": "intrusion", "dossier": str(self.leves.id)},
            format="json",
        )
        self.assertEqual(reponse.status_code, 404)


class TestConfigurationHebergement(BaseDCUHATTest):
    """La configuration doit accepter une URL de connexion telle que la
    fournissent Supabase, Render ou Neon, sans recopie manuelle."""

    def test_decomposition_d_une_url_de_connexion(self):
        from config.settings import _base_depuis_url

        reglages = _base_depuis_url(
            "postgresql://postgres.abcdefgh:mot%40de%3Apasse"
            "@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"
        )
        self.assertEqual(reglages["USER"], "postgres.abcdefgh")
        self.assertEqual(reglages["PASSWORD"], "mot@de:passe")
        self.assertEqual(reglages["HOST"], "aws-0-eu-central-1.pooler.supabase.com")
        self.assertEqual(reglages["PORT"], "5432")
        self.assertEqual(reglages["NAME"], "postgres")

    def test_url_minimale(self):
        from config.settings import _base_depuis_url

        reglages = _base_depuis_url("postgresql://user:pass@hote/dcuhat")
        self.assertEqual(reglages["PORT"], "5432")
        self.assertEqual(reglages["NAME"], "dcuhat")

    def test_le_stockage_s3_utilise_l_adressage_par_chemin(self):
        """Sans cela, ni MinIO ni Supabase ne repondent."""
        from unittest.mock import patch

        from apps.common.object_storage import StockageS3

        with patch("boto3.client") as client:
            StockageS3()
            configuration = client.call_args.kwargs["config"]
        self.assertEqual(configuration.s3["addressing_style"], "path")
        self.assertEqual(configuration.signature_version, "s3v4")
