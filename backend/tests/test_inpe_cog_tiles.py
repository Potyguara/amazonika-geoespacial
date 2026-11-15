"""Geometry-only checks for the restricted experimental GEO90B COG tile renderer."""
import math
import unittest
from deploy.inpe.cog_tiles import tile_lonlat_bbox, intersects_scene


class TestCogTileGeometry(unittest.TestCase):
    def test_equatorial_tile_bounds(self):
        w, s, e, n = tile_lonlat_bbox(10, 367, 512)
        self.assertTrue(w < e)
        self.assertTrue(s < n)
        self.assertLess(abs(n), 1)

    def test_invalid_xyz(self):
        for xyz in [(8, 1, 1), (19, 1, 1), (10, -1, 3), (10, 3, 1024)]:
            with self.assertRaises(ValueError):
                tile_lonlat_bbox(*xyz)

    def test_scene_intersection(self):
        z = 14
        lon, lat = -50.75, -0.02
        x = int((lon + 180) / 360 * (2 ** z))
        y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * (2 ** z))
        self.assertTrue(intersects_scene(z, x, y))
        self.assertFalse(intersects_scene(14, 100, 100))


if __name__ == "__main__":
    unittest.main()
