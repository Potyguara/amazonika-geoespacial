"""Testes de limites de tiles XYZ e de cobertura de ortoimagem PS4."""
import math
import unittest

from app.services.ps4_tiles import (
    WORLD_HALF, mercator_tile_bounds, tile_intersects_footprint,
)


class Ps4TilesTests(unittest.TestCase):
    def test_tiling_global_zoom_zero(self):
        bounds = mercator_tile_bounds(0, 0, 0)
        self.assertAlmostEqual(bounds[0], -WORLD_HALF)
        self.assertAlmostEqual(bounds[1], -WORLD_HALF)
        self.assertAlmostEqual(bounds[2], WORLD_HALF)
        self.assertAlmostEqual(bounds[3], WORLD_HALF)

    def test_rejeita_indices_invalidos(self):
        for values in [(-1, 0, 0), (20, 0, 0), (4, 16, 2), (4, 0, -1)]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                mercator_tile_bounds(*values)

    def test_cobertura_proxima_ao_amapa(self):
        metadata = {"wgs84_extent": {
            "type": "Polygon",
            "coordinates": [[[-52, -1], [-50, -1], [-50, 1], [-52, 1], [-52, -1]]],
        }}
        self.assertTrue(tile_intersects_footprint(metadata, 10, 366, 511))
        self.assertFalse(tile_intersects_footprint(metadata, 10, 500, 500))

    def test_sem_footprint_rejeitado(self):
        with self.assertRaises(ValueError):
            tile_intersects_footprint({}, 10, 366, 511)


if __name__ == "__main__":
    unittest.main()
