"""Support geospatial : detection de format, emprise reprojetee, recherche
spatiale et conversion."""

import io
import json

from apps.geo.models import GeoAsset, StatutExtraction
from apps.geo.tasks import analyser_fichier
from apps.storage import services

from .base import BaseDCUHATTest

# Un ilot de parcelles, en WGS84.
PARCELLES = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"parcelle": "LB-2026-014", "quartier": "Centre"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-13.6800, 9.5400], [-13.6790, 9.5400],
                    [-13.6790, 9.5410], [-13.6800, 9.5410],
                    [-13.6800, 9.5400],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {"parcelle": "LB-2026-015", "quartier": "Centre"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-13.6790, 9.5400], [-13.6780, 9.5400],
                    [-13.6780, 9.5410], [-13.6790, 9.5410],
                    [-13.6790, 9.5400],
                ]],
            },
        },
    ],
}


class TestExtractionGeospatiale(BaseDCUHATTest):
    def _deposer_geojson(self, nom="parcelles.geojson", donnees=None):
        contenu = io.BytesIO(json.dumps(donnees or PARCELLES).encode())
        fichier, _ = services.creer_ou_mettre_a_jour_fichier(
            nom=nom, dossier=self.leves, contenu=contenu, auteur=self.agent_cadastre
        )
        analyser_fichier(str(fichier.id))
        return fichier

    def test_un_geojson_est_reconnu_et_son_emprise_calculee(self):
        fichier = self._deposer_geojson()
        asset = GeoAsset.objects.get(file=fichier)
        self.assertEqual(asset.geo_format, "GEOJSON")
        self.assertEqual(asset.extraction_status, StatutExtraction.OK)
        self.assertEqual(asset.feature_count, 2)
        self.assertIsNotNone(asset.extent)
        self.assertEqual(asset.extent.srid, 4326)

    def test_le_centroide_tombe_dans_l_emprise(self):
        fichier = self._deposer_geojson()
        asset = GeoAsset.objects.get(file=fichier)
        self.assertTrue(asset.extent.contains(asset.centroid))

    def test_le_kind_est_deduit_de_l_extension(self):
        fichier = self._deposer_geojson()
        self.assertEqual(fichier.kind, "VECTEUR")
        self.assertTrue(fichier.est_geospatial)

    def test_la_geometrie_simplifiee_est_prete_pour_la_carte(self):
        fichier = self._deposer_geojson()
        asset = GeoAsset.objects.get(file=fichier)
        self.assertIsNotNone(asset.simplified_geojson)
        self.assertEqual(len(asset.simplified_geojson["features"]), 2)

    def test_un_fichier_non_geospatial_ne_cree_pas_d_asset(self):
        fichier, _ = services.creer_ou_mettre_a_jour_fichier(
            nom="note.txt", dossier=self.leves, contenu=self.contenu("texte"),
            auteur=self.agent_cadastre,
        )
        analyser_fichier(str(fichier.id))
        self.assertFalse(GeoAsset.objects.filter(file=fichier).exists())

    def test_projection_introuvable_signalee_et_non_devinee(self):
        """Un DXF sans georeferencement ne doit surtout pas etre place au
        hasard sur la carte communale."""
        dxf = (
            "0\nSECTION\n2\nENTITIES\n0\nLINE\n8\n0\n"
            "10\n100.0\n20\n200.0\n11\n150.0\n21\n250.0\n0\nENDSEC\n0\nEOF\n"
        )
        fichier, _ = services.creer_ou_mettre_a_jour_fichier(
            nom="plan.dxf", dossier=self.leves,
            contenu=io.BytesIO(dxf.encode()), auteur=self.agent_cadastre,
        )
        analyser_fichier(str(fichier.id))
        asset = GeoAsset.objects.filter(file=fichier).first()
        self.assertIsNotNone(asset)
        self.assertEqual(asset.extraction_status, StatutExtraction.PARTIAL)
        self.assertIsNone(asset.extent)
        self.assertIn("projection", asset.extraction_error.lower())


class TestRechercheSpatiale(BaseDCUHATTest):
    def setUp(self):
        super().setUp()
        contenu = io.BytesIO(json.dumps(PARCELLES).encode())
        self.fichier, _ = services.creer_ou_mettre_a_jour_fichier(
            nom="parcelles.geojson", dossier=self.leves, contenu=contenu,
            auteur=self.agent_cadastre,
        )
        analyser_fichier(str(self.fichier.id))

    def test_bbox_qui_intersecte_retourne_le_fichier(self):
        client = self.client_pour(self.agent_cadastre)
        reponse = client.get("/api/v1/geo/search/?bbox=-13.69,9.53,-13.67,9.55")
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(len(reponse.json()), 1)

    def test_bbox_eloignee_ne_retourne_rien(self):
        client = self.client_pour(self.agent_cadastre)
        reponse = client.get("/api/v1/geo/search/?bbox=2.0,48.0,2.5,48.5")
        self.assertEqual(reponse.json(), [])

    def test_la_recherche_spatiale_respecte_les_permissions(self):
        client = self.client_pour(self.agent_urbanisme)
        reponse = client.get("/api/v1/geo/search/?bbox=-13.69,9.53,-13.67,9.55")
        self.assertEqual(reponse.json(), [])

    def test_endpoint_geojson_sert_la_couche_pour_la_carte(self):
        client = self.client_pour(self.agent_cadastre)
        reponse = client.get(f"/api/v1/geo/assets/{self.fichier.id}/geojson/")
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.json()["type"], "FeatureCollection")


class TestConversion(BaseDCUHATTest):
    def test_conversion_geojson_vers_shapefile(self):
        import shutil

        if shutil.which("ogr2ogr") is None:
            self.skipTest("ogr2ogr absent de cet environnement.")
        contenu = io.BytesIO(json.dumps(PARCELLES).encode())
        fichier, _ = services.creer_ou_mettre_a_jour_fichier(
            nom="parcelles.geojson", dossier=self.leves, contenu=contenu,
            auteur=self.agent_cadastre,
        )
        analyser_fichier(str(fichier.id))
        client = self.client_pour(self.agent_cadastre)
        reponse = client.post(
            f"/api/v1/geo/assets/{fichier.id}/convert/",
            {"target_format": "SHP"}, format="json",
        )
        self.assertEqual(reponse.status_code, 202)
        self.assertEqual(reponse.json()["status"], "DONE")
        self.assertIsNotNone(reponse.json()["result_file"])

    def test_la_conversion_vers_shapefile_livre_une_archive_complete(self):
        """Un .shp seul est inutilisable : le .dbf et le .shx doivent suivre."""
        import shutil
        import zipfile

        from apps.common.object_storage import stockage
        from apps.storage.models import File

        if shutil.which("ogr2ogr") is None:
            self.skipTest("ogr2ogr absent de cet environnement.")
        contenu = io.BytesIO(json.dumps(PARCELLES).encode())
        fichier, _ = services.creer_ou_mettre_a_jour_fichier(
            nom="parcelles.geojson", dossier=self.leves, contenu=contenu,
            auteur=self.agent_cadastre,
        )
        analyser_fichier(str(fichier.id))
        client = self.client_pour(self.agent_cadastre)
        reponse = client.post(
            f"/api/v1/geo/assets/{fichier.id}/convert/",
            {"target_format": "SHP"}, format="json",
        )
        produit = File.objects.get(pk=reponse.json()["result_file"])
        self.assertTrue(produit.name.endswith(".zip"))
        with stockage().lire(produit.current_version.storage_key) as flux:
            with zipfile.ZipFile(io.BytesIO(flux.read())) as archive:
                extensions = {n.rsplit(".", 1)[-1].lower() for n in archive.namelist()}
        self.assertTrue({"shp", "dbf", "shx"}.issubset(extensions))
