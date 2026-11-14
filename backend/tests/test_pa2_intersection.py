"""GEO87: regressão de interseção PA2 com bloqueios de inferência altimétrica."""
import unittest
from app.services.pa2_intersection import intersect_pa2


class Pa2Tests(unittest.TestCase):
    def points(self):
        return [
            {"name": "A", "easting_m": 500000, "northing_m": 100000},
            {"name": "B", "easting_m": 500100, "northing_m": 100100},
            {"name": "C", "easting_m": 500000, "northing_m": 100100},
            {"name": "D", "easting_m": 500100, "northing_m": 100000},
        ]

    def test_intersection_and_no_invented_sigma(self):
        res = intersect_pa2(self.points())
        self.assertAlmostEqual(res["easting_m"], 500050)
        self.assertAlmostEqual(res["northing_m"], 100050)
        self.assertEqual(res["method"], "PA2")
        self.assertEqual(res["vertex_type"], "V")
        self.assertIsNone(res["height_m"])
        self.assertIsNone(res["sigma_e_m"])
        self.assertFalse(res["ready_for_sigef"])

    def test_reject_parallel_lines(self):
        data = self.points()
        data[2]["northing_m"] = 100200
        data[3]["northing_m"] = 100300
        with self.assertRaisesRegex(ValueError, "paralelos"):
            intersect_pa2(data)

    def test_extrapolation_warning(self):
        data = self.points()
        data[2]["northing_m"] = 100300
        data[3]["northing_m"] = 100200
        res = intersect_pa2(data)
        self.assertTrue(any("extrapola" in w for w in res["warnings"]))

    def test_reject_duplicate_testimony(self):
        data = self.points()
        data[3]["name"] = "A"
        with self.assertRaisesRegex(ValueError, "distintos"):
            intersect_pa2(data)


if __name__ == "__main__":
    unittest.main()
