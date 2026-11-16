"""O diagnóstico da imagem nunca deve converter resolução espacial em precisão."""
import unittest
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image, ImageDraw
from app.services.ps4_raster_diagnostic import analyze_raster_visual

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

    @unittest.skipUnless(shutil.which("gdal_translate") and shutil.which("gdalinfo"),
                         "GDAL CLI indisponível")
    def test_analise_real_da_banda_sem_inventar_precisao(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic-raster.tif"
            image = Image.new("L", (256, 128), 24)
            brush = ImageDraw.Draw(image)
            brush.rectangle((128, 0, 255, 127), fill=220)
            image.save(path)
            analysis = analyze_raster_visual(path)
        self.assertEqual(analysis["status"], "ANALYZED")
        self.assertEqual(analysis["quality_basis"],
                         "DIAGNOSTICO_RADIOMETRICO_EXPLORATORIO")
        self.assertIsNone(analysis["positional_accuracy_m"])
        self.assertIsNone(analysis["sigma_e_m"])
        self.assertIsNone(analysis["sigma_n_m"])
        self.assertGreater(analysis["grayscale_stddev"], 0)

    def test_sem_crs_nao_e_aprovado(self):
        with self.assertRaises(ValueError):
            diagnose_ps4_raster({**META, "crs_authority": None}, [])


if __name__ == "__main__":
    unittest.main()
