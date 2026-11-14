"""GEO88: testes matemáticos PA1/PT8; nenhum sigma/altura inventado."""
import math
import unittest
from app.services.constructed_vertices import calculate_constructed_vertex


WITNESSES = [
    {"name": "A", "easting_m": 500000, "northing_m": 100000},
    {"name": "B", "easting_m": 500100, "northing_m": 100000},
]


class ConstructedMethodsTests(unittest.TestCase):
    def test_pa1_left_offset(self):
        v = calculate_constructed_vertex("PA1", WITNESSES, 12.5, "LEFT")
        self.assertAlmostEqual(v["easting_m"], 500000)
        self.assertAlmostEqual(v["northing_m"], 100012.5)
        self.assertEqual(v["vertex_type"], "V")
        self.assertIsNone(v["height_m"])
        self.assertIsNone(v["sigma_e_m"])
        self.assertFalse(v["ready_for_sigef"])

    def test_pa1_right_offset(self):
        v = calculate_constructed_vertex("PA1", WITNESSES, 7.5, "RIGHT")
        self.assertAlmostEqual(v["northing_m"], 99992.5)

    def test_pt8_forward_from_first_point(self):
        v = calculate_constructed_vertex("PT8", WITNESSES, 25, "FORWARD")
        self.assertAlmostEqual(v["easting_m"], 500025)
        self.assertAlmostEqual(v["northing_m"], 100000)
        self.assertEqual(v["vertex_type"], "P")
        self.assertFalse(v["ready_for_sigef"])

    def test_pt8_backward(self):
        v = calculate_constructed_vertex("PT8", WITNESSES, 25, "BACKWARD")
        self.assertAlmostEqual(v["easting_m"], 499975)

    def test_reject_missing_distance(self):
        with self.assertRaises(ValueError):
            calculate_constructed_vertex("PT8", WITNESSES, None, "FORWARD")

    def test_reject_duplicate_testimony(self):
        with self.assertRaisesRegex(ValueError, "diferentes"):
            calculate_constructed_vertex("PA1", [WITNESSES[0], WITNESSES[0]], 4, "LEFT")

    def test_reject_zero_alignment(self):
        with self.assertRaises(ValueError):
            calculate_constructed_vertex("PA1", [
                {"name": "A", "easting_m": 500000, "northing_m": 100000},
                {"name": "B", "easting_m": 500000, "northing_m": 100000},
            ], 5, "LEFT")

    def test_geographic_only_after_confirmation(self):
        a = calculate_constructed_vertex("PA1", WITNESSES, 5, "LEFT")
        self.assertIsNone(a["latitude"])
        b = calculate_constructed_vertex(
            "PA1", WITNESSES, 5, "LEFT",
            utm_zone=22, hemisphere="N", sirgas2000_confirmed=True,
        )
        self.assertTrue(math.isfinite(b["longitude"]))
        self.assertTrue(math.isfinite(b["latitude"]))


if __name__ == "__main__":
    unittest.main()
