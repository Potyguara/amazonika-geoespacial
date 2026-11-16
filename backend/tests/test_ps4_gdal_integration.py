"""Integração GDAL real: raster local sintético -> PNG XYZ privado."""
from io import BytesIO
from pathlib import Path
from shutil import which
from tempfile import TemporaryDirectory
import subprocess
import unittest
from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from app.services.ps4_assets import store_uploaded_asset, stored_file_path
from app.services.ps4_tiles import render_png_tile, tile_intersects_footprint


@unittest.skipUnless(
    all(which(x) for x in ("gdal_translate", "gdalwarp", "gdalinfo")),
    "GDAL CLI é obrigatório para a integração raster",
)
class PS4GdalRasterIntegrationTests(unittest.TestCase):
    def test_geotiff_geo_referenciado_gera_tile_png(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            original = root / "sample.png"
            Image.new("RGB", (80, 80), (30, 160, 80)).save(original)
            tiff = root / "sample.tif"
            subprocess.run(
                ["gdal_translate", "-q", "-of", "GTiff",
                 "-a_srs", "EPSG:4326",
                 "-a_ullr", "-52", "1", "-50", "-1",
                 str(original), str(tiff)],
                check=True,
            )
            uid, pid = uuid4(), uuid4()
            with patch("app.services.ps4_assets.get_settings",
                       return_value=SimpleNamespace(storage_dir=root)):
                record = store_uploaded_asset(
                    BytesIO(tiff.read_bytes()), uid, pid, "raster",
                )
                self.assertEqual(record["metadata"]["driver"], "GTiff")
                self.assertTrue(tile_intersects_footprint(
                    record["metadata"], 10, 366, 511,
                ))
                location = stored_file_path(uid, pid, "raster", record["sha256"])
                image = render_png_tile(location, 10, 366, 511)
                self.assertTrue(image.startswith(b"\\x89PNG\\r\\n\\x1a\\n"))
                with Image.open(BytesIO(image)) as tile:
                    self.assertEqual(tile.size, (256, 256))
                    self.assertIn(tile.mode, {"RGB", "RGBA"})


if __name__ == "__main__":
    unittest.main()
