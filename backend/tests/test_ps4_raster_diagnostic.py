"""O diagnóstico da imagem nunca deve converter resolução espacial em precisão."""
import unittest

from app.services.ps4_raster_diagnostic import diagnose_ps4_raster


META = {
    "crs_authority": "EPSG:32622", "width": 1097, "height": 773,
    "geo_transform": [513000.0, 2.0, 0.0, 45500.0, 0.0, -2.0],
    "wgs84_extent": {
        "type": "Polygon", "coordinates": [[
            [-51.0, 0.3], [-50.8, 0.3], [-50.8, 0.5],
            [-51.0, 0.5], [-51.0, 0.3],
        ]]
    },
}


class RasterDiagnosticTests(unittest.TestCase):
    def test_cobertura_mas_sem_rms(self):
        result = diagnose_ps4_raster(META, [
            {"name": "V1", "longitude": -50.9, "latitude": 0.4},
        ])
        self.assertEqual(result["status"], "RASTER_STRUCTURALLY_VALID")
        self.assertEqual(result["vertices_inside"], 1)
        self.assertEqual(result["pixel_size_x_m"], 2)
        self.assertEqual(result["accuracy_status"], "UNVERIFIED")
        self.assertIsNone(result["horizontal_rms_m"])
        self.assertIsNone(result["sigma_lat_m"])

    def test_fora_da_cobertura(self):
        result = diagnose_ps4_raster(META, [
            {"name": "V1", "longitude": -50.9, "latitude": 0.4},
            {"name": "V2", "longitude": -50.5, "latitude": 0.4},
        ])
        self.assertEqual(result["status"], "COVERAGE_INCOMPLETE")
        self.assertEqual(result["vertices_outside"], ["V2"])
        self.assertEqual(result["vertices_inside"], 1)

    def test_sem_crs_nao_e_aprovado(self):
        with self.assertRaises(ValueError):
            diagnose_ps4_raster({**META, "crs_authority": None}, [])


if __name__ == "__main__":
    unittest.main()
