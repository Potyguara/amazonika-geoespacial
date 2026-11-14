"""Conferência vertical: h é preservada no SIGEF, HN é calculada."""
import unittest

from app.services.vertical_datum import convert_altitudes


def point():
    return {
        "name": "0304",
        "latitude": 0.25, "longitude": -51.3,
        "ellipsoidal_height_m": 20.4, "conversion_factor_m": 13.2,
        "factor_origin": "hgeoHNOR2020 IBGE - entrada manual verificada",
        "height_reference_confirmed": True, "sigma_h_m": 0.03,
    }


class VerticalDatumTests(unittest.TestCase):
    def test_normal_height_and_sigef_height_preserved(self):
        original = point()
        result = convert_altitudes([original], model="hgeoHNOR2020")
        self.assertEqual(result["status"], "READY", result["errors"])
        actual = result["points"][0]
        self.assertAlmostEqual(actual["normal_height_m"], 7.2)
        self.assertAlmostEqual(actual["sigef_h_m"], 20.4)
        self.assertEqual(original["ellipsoidal_height_m"], 20.4)
        self.assertEqual(actual["sigef_height_type"], "ELLIPSOIDAL")

    def test_orthometric_model_is_distinct(self):
        result = convert_altitudes([point()], model="MAPGEO2015")
        self.assertEqual(result["status"], "READY")
        self.assertIn("orthometric_height_m", result["points"][0])
        self.assertNotIn("normal_height_m", result["points"][0])

    def test_rejects_unconfirmed_ellipsoidal_height(self):
        value = point()
        value["height_reference_confirmed"] = False
        result = convert_altitudes([value], model="hgeoHNOR2020")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertIn("altura elipsoidal", result["errors"][0])

    def test_rejects_missing_factor(self):
        value = point()
        del value["conversion_factor_m"]
        result = convert_altitudes([value], model="hgeoHNOR2020")
        self.assertEqual(result["status"], "INCOMPLETE")

    def test_allows_negative_ellipsoidal_heights(self):
        value = point()
        value["ellipsoidal_height_m"] = -2.4
        result = convert_altitudes([value], model="hgeoHNOR2020")
        self.assertEqual(result["status"], "READY")
        self.assertAlmostEqual(result["points"][0]["normal_height_m"], -15.6)

    def test_rejects_unrecorded_factor_origin(self):
        value = point()
        value["factor_origin"] = ""
        result = convert_altitudes([value], model="hgeoHNOR2020")
        self.assertEqual(result["status"], "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
