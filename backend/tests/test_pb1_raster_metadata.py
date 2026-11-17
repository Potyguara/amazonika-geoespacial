"""GEO96: metadados PB1 não confundem SRC horizontal com datum vertical."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from pyproj import CRS
from app.services.ps4_assets import _raster_info


class PB1RasterMetadataTests(unittest.TestCase):
    def _mock_gdal(self, metadata=None):
        info = {
            "driverShortName": "GTiff",
            "size": [608, 759],
            "coordinateSystem": {"wkt": CRS.from_epsg(31982).to_wkt()},
            "geoTransform": [458000, 2.5, 0, 25500, 0, -2.5],
            "bands": [{"type": "Float32", "noDataValue": -3.40282346639e38}],
            "metadata": {"": metadata or {}},
        }
        return SimpleNamespace(returncode=0, stdout=json.dumps(info))

    def test_horizontal_utm_nao_cria_datum_vertical(self):
        with patch("app.services.ps4_assets.subprocess.run", return_value=self._mock_gdal()):
            info = _raster_info(Path("MDT_cinza.tif"))
        self.assertEqual(info["crs_authority"], "EPSG:31982")
        self.assertIsNone(info["vertical_crs_name"])
        self.assertEqual(info["embedded_source_tags"], {})
        self.assertNotIn("pec_class", info)

    def test_documentacao_so_quando_embutida(self):
        tags = {
            "TIFFTAG_IMAGEDESCRIPTION": "Mosaico MDT de teste; datum vertical nao declarado",
            "TIFFTAG_COPYRIGHT": "Origem informada pelo produtor",
            "UNVERIFIED_PEC": "A",
        }
        with patch("app.services.ps4_assets.subprocess.run", return_value=self._mock_gdal(tags)):
            info = _raster_info(Path("MDT_cinza.tif"))
        self.assertIn("TIFFTAG_IMAGEDESCRIPTION", info["embedded_source_tags"])
        self.assertNotIn("UNVERIFIED_PEC", info["embedded_source_tags"])
        self.assertIsNone(info["vertical_crs_name"])


if __name__ == "__main__":
    unittest.main()
