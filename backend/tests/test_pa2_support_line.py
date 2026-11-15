"""Testes do procedimento PA2 com dois marcos e clique projetado."""
import unittest
from pyproj import Transformer
from app.services.pa2_support_line import pa2_support_line

TRANS = Transformer.from_crs("EPSG:31976", "EPSG:4674", always_xy=True)
A = {"name": "M001", "easting_m": 500000, "northing_m": 100000,
     "physical_altitude_m": 20, "sigma_e_m": 0.02, "sigma_n_m": 0.04,
     "sigma_h_m": 0.06}
B = {"name": "M002", "easting_m": 500100, "northing_m": 100000,
     "physical_altitude_m": 40, "sigma_e_m": 0.04, "sigma_n_m": 0.06,
     "sigma_h_m": 0.08}


def payload():
    lon, lat = TRANS.transform(500025, 100004)
    return {"supports": [A, B], "hint_longitude": lon, "hint_latitude": lat,
            "utm_zone": 22, "hemisphere": "N",
            "sirgas2000_confirmed": True, "altitude_type": "HN"}


class PA2SupportLineTests(unittest.TestCase):
    def test_interpolates_physical_height_and_sigmas(self):
        p = pa2_support_line(payload())
        self.assertAlmostEqual(p["easting_m"], 500025, places=3)
        self.assertAlmostEqual(p["northing_m"], 100000, places=3)
        self.assertAlmostEqual(p["physical_altitude_m"], 25)
        self.assertAlmostEqual(p["sigma_e_m"], 0.03)
        self.assertAlmostEqual(p["sigma_n_m"], 0.05)
        self.assertAlmostEqual(p["sigma_h_m"], 0.07)
        self.assertIsNone(p["height_m"])
        self.assertFalse(p["ready_for_sigef"])

    def test_missing_sigma_keeps_null(self):
        inp = payload()
        inp["supports"] = [A, {**B, "sigma_e_m": None}]
        p = pa2_support_line(inp)
        self.assertIsNone(p["sigma_e_m"])

    def test_incompatible_physical_model_fails(self):
        inp = payload()
        inp["altitude_type"] = "XYZ"
        with self.assertRaises(ValueError):
            pa2_support_line(inp)

    def test_outside_segment_fails(self):
        inp = payload()
        inp["hint_longitude"], inp["hint_latitude"] = TRANS.transform(500120, 100000)
        with self.assertRaisesRegex(ValueError, "fora do segmento"):
            pa2_support_line(inp)

    def test_no_ellipsoidal_from_physical_height(self):
        p = pa2_support_line(payload())
        self.assertNotIn("ellipsoidal_height_m", p)
        self.assertIsNone(p["height_m"])


if __name__ == "__main__":
    unittest.main()
