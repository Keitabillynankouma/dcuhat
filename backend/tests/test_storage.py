"""Cycle de vie des fichiers : versionnement, quota, corbeille, televersement
fragmente."""

import base64
import hashlib
import io

from django.test import override_settings

from apps.common.exceptions import ConflitDeNom, QuotaDepasse
from apps.storage import services
from apps.storage.models import File, FileVersion, Folder

from .base import BaseDCUHATTest


class TestVersionnement(BaseDCUHATTest):
    def test_une_modification_empile_une_version(self):
        fichier, v1 = services.creer_ou_mettre_a_jour_fichier(
            nom="leve.txt", dossier=self.leves,
            contenu=self.contenu("premiere mesure"), auteur=self.agent_cadastre,
        )
        fichier, v2 = services.creer_ou_mettre_a_jour_fichier(
            nom="leve.txt", dossier=self.leves,
            contenu=self.contenu("mesure corrigee"), auteur=self.agent_cadastre,
            commentaire="correction d'altimetrie",
        )
        self.assertEqual(v1.version_number, 1)
        self.assertEqual(v2.version_number, 2)
        self.assertEqual(fichier.versions.count(), 2)
        self.assertEqual(fichier.current_version_id, v2.id)

    def test_le_contenu_precedent_reste_lisible(self):
        from apps.common.object_storage import stockage

        fichier, v1 = services.creer_ou_mettre_a_jour_fichier(
            nom="leve.txt", dossier=self.leves, contenu=self.contenu("version A"),
            auteur=self.agent_cadastre,
        )
        services.creer_ou_mettre_a_jour_fichier(
            nom="leve.txt", dossier=self.leves, contenu=self.contenu("version B"),
            auteur=self.agent_cadastre,
        )
        with stockage().lire(v1.storage_key) as flux:
            self.assertEqual(flux.read().decode(), "version A")

    def test_restaurer_une_version_ancienne_cree_une_nouvelle_version(self):
        fichier, _ = services.creer_ou_mettre_a_jour_fichier(
            nom="plan.txt", dossier=self.leves, contenu=self.contenu("A"),
            auteur=self.agent_cadastre,
        )
        services.creer_ou_mettre_a_jour_fichier(
            nom="plan.txt", dossier=self.leves, contenu=self.contenu("B"),
            auteur=self.agent_cadastre,
        )
        version = services.restaurer_version(fichier, 1, self.agent_cadastre)
        fichier.refresh_from_db()
        self.assertEqual(version.version_number, 3)
        self.assertEqual(fichier.current_version.checksum_sha256, version.checksum_sha256)
        self.assertEqual(fichier.versions.count(), 3)

    def test_deduplication_par_checksum(self):
        f1, v1 = services.creer_ou_mettre_a_jour_fichier(
            nom="a.txt", dossier=self.leves, contenu=self.contenu("identique"),
            auteur=self.agent_cadastre,
        )
        f2, v2 = services.creer_ou_mettre_a_jour_fichier(
            nom="b.txt", dossier=self.leves, contenu=self.contenu("identique"),
            auteur=self.agent_cadastre,
        )
        self.assertEqual(v1.checksum_sha256, v2.checksum_sha256)
        self.assertEqual(v1.storage_key, v2.storage_key)


class TestQuota(BaseDCUHATTest):
    def test_le_quota_est_refuse_avant_transfert(self):
        gros = io.BytesIO(b"x" * (11 * 1024 * 1024))  # quota du service : 10 Mo
        with self.assertRaises(QuotaDepasse):
            services.creer_ou_mettre_a_jour_fichier(
                nom="orthophoto.txt", dossier=self.leves, contenu=gros,
                auteur=self.agent_cadastre,
            )
        self.assertFalse(File.objects.filter(name="orthophoto.txt").exists())

    def test_init_de_televersement_refuse_des_l_annonce_de_la_taille(self):
        client = self.client_pour(self.agent_cadastre)
        reponse = client.post(
            "/api/v1/files/upload/init/",
            {"nom": "gros.tif", "dossier": str(self.leves.id), "taille": 50 * 1024 * 1024},
            format="json",
        )
        self.assertEqual(reponse.status_code, 413)
        self.assertEqual(reponse.json()["code"], "QUOTA_EXCEEDED")


class TestNommage(BaseDCUHATTest):
    def test_conflit_de_nom_refuse_en_creation_directe(self):
        services.creer_dossier(nom="Campagne", parent=self.leves, auteur=self.agent_cadastre)
        with self.assertRaises(ConflitDeNom):
            services.creer_dossier(
                nom="Campagne", parent=self.leves, auteur=self.agent_cadastre
            )

    def test_nom_disponible_suffixe_sans_echouer(self):
        services.creer_dossier(nom="Campagne", parent=self.leves, auteur=self.agent_cadastre)
        propose = services.nom_disponible("Campagne", dossier=self.leves, modele=Folder)
        self.assertEqual(propose, "Campagne (2)")

    def test_nom_de_fichier_nettoye(self):
        fichier, _ = services.creer_ou_mettre_a_jour_fichier(
            nom="plan/2026:secteur*3.txt", dossier=self.leves,
            contenu=self.contenu(), auteur=self.agent_cadastre,
        )
        self.assertEqual(fichier.name, "plan_2026_secteur_3.txt")

    def test_executable_refuse(self):
        from apps.common.exceptions import OperationInvalide

        with self.assertRaises(OperationInvalide):
            services.creer_ou_mettre_a_jour_fichier(
                nom="outil.txt", dossier=self.leves,
                contenu=io.BytesIO(b"MZ\x90\x00charge utile"),
                auteur=self.agent_cadastre,
            )


class TestArborescence(BaseDCUHATTest):
    def test_le_chemin_suit_le_renommage_du_parent(self):
        enfant = services.creer_dossier(
            nom="2026", parent=self.leves, auteur=self.chef_cadastre
        )
        petit_enfant = services.creer_dossier(
            nom="Secteur 3", parent=enfant, auteur=self.chef_cadastre
        )
        services.renommer_dossier(self.leves, "Leves 2026", self.chef_cadastre)
        petit_enfant.refresh_from_db()
        self.assertTrue(petit_enfant.path.startswith("/cadastre/leves-2026/"))

    def test_un_dossier_ne_peut_pas_etre_deplace_dans_lui_meme(self):
        from apps.common.exceptions import OperationInvalide

        enfant = services.creer_dossier(
            nom="2026", parent=self.leves, auteur=self.chef_cadastre
        )
        with self.assertRaises(OperationInvalide):
            services.deplacer_dossier(self.leves, enfant, self.chef_cadastre)

    def test_la_corbeille_emporte_le_sous_arbre_et_le_restitue(self):
        enfant = services.creer_dossier(
            nom="2026", parent=self.leves, auteur=self.chef_cadastre
        )
        fichier, _ = services.creer_ou_mettre_a_jour_fichier(
            nom="note.txt", dossier=enfant, contenu=self.contenu(),
            auteur=self.chef_cadastre,
        )
        self.leves.mettre_a_la_corbeille(self.chef_cadastre)
        enfant.refresh_from_db()
        fichier.refresh_from_db()
        self.assertTrue(enfant.is_deleted)
        self.assertTrue(fichier.is_deleted)

        self.leves.restaurer()
        enfant.refresh_from_db()
        fichier.refresh_from_db()
        self.assertFalse(enfant.is_deleted)
        self.assertFalse(fichier.is_deleted)


class TestTeleversementFragmente(BaseDCUHATTest):
    @override_settings(UPLOAD_CHUNK_SIZE_MB=1)
    def test_televersement_en_fragments_puis_assemblage(self):
        client = self.client_pour(self.agent_cadastre)
        contenu = b"A" * (2 * 1024 * 1024 + 512)
        empreinte = hashlib.sha256(contenu).hexdigest()

        init = client.post(
            "/api/v1/files/upload/init/",
            {
                "nom": "leve-terrain.txt",
                "dossier": str(self.leves.id),
                "taille": len(contenu),
                "checksum_sha256": empreinte,
            },
            format="json",
        )
        self.assertEqual(init.status_code, 201)
        upload_id = init.json()["upload_id"]
        taille_fragment = init.json()["chunk_size"]
        total = init.json()["total_chunks"]
        self.assertEqual(total, 3)

        for numero in range(1, total + 1):
            morceau = contenu[(numero - 1) * taille_fragment: numero * taille_fragment]
            reponse = client.put(
                f"/api/v1/files/upload/{upload_id}/part/{numero}/",
                data=morceau,
                content_type="application/octet-stream",
            )
            self.assertEqual(reponse.status_code, 200)

        fin = client.post(f"/api/v1/files/upload/{upload_id}/complete/")
        self.assertEqual(fin.status_code, 201)
        fichier = File.objects.get(pk=fin.json()["id"])
        self.assertEqual(fichier.size_bytes, len(contenu))
        self.assertEqual(fichier.current_version.checksum_sha256, empreinte)

    @override_settings(UPLOAD_CHUNK_SIZE_MB=1)
    def test_un_complete_rejoue_ne_cree_pas_de_doublon(self):
        client = self.client_pour(self.agent_cadastre)
        contenu = b"B" * 1024
        init = client.post(
            "/api/v1/files/upload/init/",
            {"nom": "note.txt", "dossier": str(self.leves.id), "taille": len(contenu)},
            format="json",
        ).json()
        client.put(
            f"/api/v1/files/upload/{init['upload_id']}/part/1/",
            data=contenu, content_type="application/octet-stream",
        )
        premier = client.post(f"/api/v1/files/upload/{init['upload_id']}/complete/")
        second = client.post(f"/api/v1/files/upload/{init['upload_id']}/complete/")
        self.assertEqual(premier.json()["id"], second.json()["id"])
        self.assertEqual(File.objects.filter(name="note.txt").count(), 1)

    @override_settings(UPLOAD_CHUNK_SIZE_MB=1)
    def test_fragment_manquant_signale_precisement(self):
        client = self.client_pour(self.agent_cadastre)
        contenu = b"C" * (2 * 1024 * 1024)
        init = client.post(
            "/api/v1/files/upload/init/",
            {"nom": "gros.txt", "dossier": str(self.leves.id), "taille": len(contenu)},
            format="json",
        ).json()
        client.put(
            f"/api/v1/files/upload/{init['upload_id']}/part/1/",
            data=contenu[:1024 * 1024], content_type="application/octet-stream",
        )
        fin = client.post(f"/api/v1/files/upload/{init['upload_id']}/complete/")
        self.assertEqual(fin.status_code, 400)
        self.assertIn("2", str(fin.json()["detail"]))
