import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace
from app.services.cartographic_catalog import BaseProfile,list_profiles,save_profile

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
            with self.assertRaises(ValueError):
                save_profile("user-b",BaseProfile(name="Não permitido"),p["id"])
            with self.assertRaises(ValueError):
                save_profile("user-a",BaseProfile(name="Não permitido"),seed["id"])
