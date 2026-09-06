"""Synchronisation hors ligne.

La regle testee ici est la promesse centrale du cahier des charges : une
synchronisation ne detruit jamais un travail de terrain.
"""

import base64
import uuid

from django.utils import timezone

from apps.accounts.models import Device
from apps.sharing.models import Niveau, Permission
from apps.storage import services
from apps.storage.models import File, Folder
from apps.sync.models import StatutOperation, SyncOperation
from apps.sync.services import appliquer_lot

from .base import BaseDCUHATTest


def operation(op_type, target_type, target_id, **extra):
    base = {
        "id": str(uuid.uuid4()),
        "op_type": op_type,
        "target_type": target_type,
        "target_id": str(target_id),
        "client_seq": extra.pop("client_seq", 1),
        "client_timestamp": timezone.now(),
        "payload": extra.pop("payload", {}),
    }
    base.update(extra)
    return base


class TestSynchronisation(BaseDCUHATTest):
    def setUp(self):
        super().setUp()
        self.appareil = Device.objects.create(
            user=self.agent_cadastre, label="Tablette terrain 02", platform="Android"
        )

    def test_creation_de_dossier_hors_ligne_conserve_l_identifiant_client(self):
        identifiant = uuid.uuid4()
        resultats = appliquer_lot(
            [
                operation(
                    "CREATE_FOLDER", "FOLDER", identifiant,
                    payload={"name": "Sortie du 12 mars", "parent": str(self.leves.id)},
                )
            ],
            self.agent_cadastre,
            self.appareil,
        )
        self.assertEqual(resultats[0]["status"], StatutOperation.APPLIED)
        self.assertTrue(Folder.objects.filter(pk=identifiant).exists())

    def test_rejeu_d_un_lot_est_sans_effet(self):
        lot = [
            operation(
                "CREATE_FOLDER", "FOLDER", uuid.uuid4(),
                payload={"name": "Sortie", "parent": str(self.leves.id)},
            )
        ]
        appliquer_lot(lot, self.agent_cadastre, self.appareil)
        resultats = appliquer_lot(lot, self.agent_cadastre, self.appareil)
        self.assertTrue(resultats[0].get("rejeu"))
        self.assertEqual(Folder.objects.filter(parent=self.leves, name="Sortie").count(), 1)

    def test_conflit_de_version_conserve_les_deux(self):
        fichier, v1 = services.creer_ou_mettre_a_jour_fichier(
            nom="leve.txt", dossier=self.leves, contenu=self.contenu("terrain v1"),
            auteur=self.agent_cadastre,
        )
        # Un collegue modifie le fichier au bureau pendant la sortie terrain.
        services.creer_ou_mettre_a_jour_fichier(
            nom="leve.txt", dossier=self.leves, contenu=self.contenu("bureau v2"),
            auteur=self.chef_cadastre,
        )
        resultats = appliquer_lot(
            [
                operation(
                    "UPLOAD_VERSION", "FILE", fichier.id,
                    base_version=1,
                    payload={"contenu_base64": base64.b64encode(b"terrain v1 corrige").decode()},
                )
            ],
            self.agent_cadastre,
            self.appareil,
        )
        fichier.refresh_from_db()
        self.assertEqual(resultats[0]["status"], StatutOperation.CONFLICT)
        self.assertEqual(resultats[0]["resolution"], "BOTH_KEPT")
        self.assertEqual(fichier.versions.count(), 3)
        self.assertTrue(fichier.versions.filter(is_conflict_copy=True).exists())

    def test_le_conflit_notifie_l_agent(self):
        from apps.notifications.models import Notification

        fichier, _ = services.creer_ou_mettre_a_jour_fichier(
            nom="leve.txt", dossier=self.leves, contenu=self.contenu("v1"),
            auteur=self.agent_cadastre,
        )
        services.creer_ou_mettre_a_jour_fichier(
            nom="leve.txt", dossier=self.leves, contenu=self.contenu("v2"),
            auteur=self.chef_cadastre,
        )
        appliquer_lot(
            [
                operation(
                    "UPLOAD_VERSION", "FILE", fichier.id, base_version=1,
                    payload={"contenu_base64": base64.b64encode(b"terrain").decode()},
                )
            ],
            self.agent_cadastre, self.appareil,
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.agent_cadastre, type="CONFLIT_SYNC"
            ).exists()
        )

    def test_fichier_supprime_au_bureau_et_modifie_sur_le_terrain_est_restaure(self):
        fichier, _ = services.creer_ou_mettre_a_jour_fichier(
            nom="parcelle.txt", dossier=self.leves, contenu=self.contenu("mesure"),
            auteur=self.agent_cadastre,
        )
        fichier.mettre_a_la_corbeille(self.chef_cadastre)
        appliquer_lot(
            [
                operation(
                    "UPLOAD_VERSION", "FILE", fichier.id, base_version=1,
                    payload={"contenu_base64": base64.b64encode(b"mesure terrain").decode()},
                )
            ],
            self.agent_cadastre, self.appareil,
        )
        fichier.refresh_from_db()
        self.assertFalse(fichier.is_deleted)

    def test_permission_perdue_rejette_sans_perdre_le_contenu_local(self):
        Permission.objects.create(
            folder=self.leves, grantee_user=self.agent_urbanisme, level=Niveau.WRITE,
            granted_by=self.chef_cadastre,
        )
        appareil = Device.objects.create(user=self.agent_urbanisme, label="Poste 4")
        identifiant = uuid.uuid4()
        Permission.objects.all().delete()  # le droit est retire pendant la sortie
        resultats = appliquer_lot(
            [
                operation(
                    "CREATE_FOLDER", "FOLDER", identifiant,
                    payload={"name": "Sortie", "parent": str(self.leves.id)},
                )
            ],
            self.agent_urbanisme, appareil,
        )
        self.assertEqual(resultats[0]["status"], StatutOperation.REJECTED)
        self.assertIn("Droit", resultats[0]["error"])

    def test_nom_deja_pris_est_suffixe_au_lieu_d_echouer(self):
        services.creer_dossier(nom="Sortie", parent=self.leves, auteur=self.chef_cadastre)
        resultats = appliquer_lot(
            [
                operation(
                    "CREATE_FOLDER", "FOLDER", uuid.uuid4(),
                    payload={"name": "Sortie", "parent": str(self.leves.id)},
                )
            ],
            self.agent_cadastre, self.appareil,
        )
        self.assertEqual(resultats[0]["status"], StatutOperation.APPLIED)
        self.assertEqual(resultats[0]["name"], "Sortie (2)")

    def test_les_operations_sont_appliquees_dans_l_ordre_du_client(self):
        parent = uuid.uuid4()
        enfant = uuid.uuid4()
        lot = [
            operation(
                "CREATE_FOLDER", "FOLDER", enfant, client_seq=2,
                payload={"name": "Secteur 3", "parent": str(parent)},
            ),
            operation(
                "CREATE_FOLDER", "FOLDER", parent, client_seq=1,
                payload={"name": "Campagne", "parent": str(self.leves.id)},
            ),
        ]
        appliquer_lot(lot, self.agent_cadastre, self.appareil)
        self.assertTrue(Folder.objects.filter(pk=enfant, parent_id=parent).exists())


class TestDelta(BaseDCUHATTest):
    def test_le_delta_ne_renvoie_que_le_perimetre_visible(self):
        services.creer_ou_mettre_a_jour_fichier(
            nom="cadastre.txt", dossier=self.leves, contenu=self.contenu(),
            auteur=self.agent_cadastre,
        )
        services.creer_ou_mettre_a_jour_fichier(
            nom="urbanisme.txt", dossier=self.racine_urbanisme, contenu=self.contenu(),
            auteur=self.agent_urbanisme,
        )
        client = self.client_pour(self.agent_cadastre)
        donnees = client.get("/api/v1/sync/delta/?cursor=0").json()
        chemins = {c["folder_path"] for c in donnees["changements"]}
        self.assertIn(self.leves.path, chemins)
        self.assertNotIn(self.racine_urbanisme.path, chemins)

    def test_le_curseur_avance_et_ne_rejoue_pas(self):
        client = self.client_pour(self.agent_cadastre)
        services.creer_dossier(nom="A", parent=self.leves, auteur=self.agent_cadastre)
        premier = client.get("/api/v1/sync/delta/?cursor=0").json()
        curseur = premier["cursor"]
        second = client.get(f"/api/v1/sync/delta/?cursor={curseur}").json()
        self.assertEqual(second["changements"], [])

    def test_le_manifeste_donne_version_et_empreinte(self):
        fichier, version = services.creer_ou_mettre_a_jour_fichier(
            nom="leve.txt", dossier=self.leves, contenu=self.contenu(),
            auteur=self.agent_cadastre,
        )
        client = self.client_pour(self.agent_cadastre)
        donnees = client.get("/api/v1/sync/manifest/").json()
        entree = next(f for f in donnees["fichiers"] if f["id"] == str(fichier.id))
        self.assertEqual(entree["checksum"], version.checksum_sha256)
        self.assertEqual(entree["version"], 1)
