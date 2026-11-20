import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace
from app.services.cartographic_catalog import BaseProfile,list_profiles,save_profile,delete_profile

class CatalogTests(unittest.TestCase):
    def test_catalog_lifecycle(self):
        with TemporaryDirectory() as temp, patch("app.services.cartographic_catalog.get_settings",return_value=SimpleNamespace(storage_dir=Path(temp))):
            seed=list_profiles("user-a")[0]
            self.assertEqual(seed["id"],"amapa-reference")
            self.assertEqual(seed["pec"],"")
            self.assertEqual(seed["vertical_reference"],"")
            p=save_profile("user-a",BaseProfile(name="Base de teste",producer="Órgão",product="MDT"))
            self.assertIn("Órgão",p["report_credit"])
            self.assertIn("Órgão",p["map_credit"])
            self.assertEqual(len(list_profiles("user-b")),1)
            revised=save_profile("user-a",BaseProfile(name="Revisada"),p["id"])
            self.assertEqual(revised["revision"],2)
            self.assertEqual(len(list_profiles("user-a")),2)
            self.assertTrue(list_profiles("user-a")[0]["reference_sheet"].startswith("Articulação Sistemática"))
            with self.assertRaises(ValueError):
                delete_profile("user-a",seed["id"])
            with self.assertRaises(ValueError):
                delete_profile("user-b",p["id"])
            deleted=delete_profile("user-a",p["id"])
            self.assertEqual(deleted["deleted"],p["id"])
            self.assertEqual(len(list_profiles("user-a")),1)
            with self.assertRaises(ValueError):
                save_profile("user-b",BaseProfile(name="Não permitido"),p["id"])
            with self.assertRaises(ValueError):
                save_profile("user-a",BaseProfile(name="Não permitido"),seed["id"])
