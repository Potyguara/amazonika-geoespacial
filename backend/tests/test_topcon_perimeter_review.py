"""Testes da revisão de perímetro Topcon sem acesso ao banco."""
import unittest

from app.services.topcon_perimeter_review import review_topcon_perimeter


def point(name, lon, lat, code, role="BOUNDARY"):
    return {
        "name": name, "longitude": lon, "latitude": lat,
        "point_role": role, "sigef_vertex_code": code,
        "sigef_method": "PG1", "boundary_type": "LA6",
        "confrontant": "Confrontante confirmado",
        "ellipsoidal_height_m": 12.5, "sigma_hz_m": 0.012,
        "height_reference_confirmed": True,
        "sigma_lon_m": 0.007, "sigma_lat_m": 0.009, "sigma_h_m": 0.02,
        "elevation_reported_m": 999.0,
    }


# Vértice inicial mais ao norte; depois percurso horário.
VALID = [
    point("0304", -50.8, 1.2, "TEST-M-0001"),
    point("0305", -50.79, 1.19, "TEST-M-0002"),
    point("0306", -50.81, 1.19, "TEST-M-0003"),
]


class TopconPerimeterReviewTests(unittest.TestCase):
    def test_valid_review_produces_closed_geojson(self):
        result = review_topcon_perimeter(VALID)
        self.assertTrue(result["ready_for_ods"], result["errors"])
        self.assertEqual(result["vertex_count"], 3)
        self.assertEqual(result["geometry"]["coordinates"][0][0],
                         result["geometry"]["coordinates"][0][-1])
        self.assertGreater(result["area_ha"], 0)

    def test_confirmed_individual_sigmas_enable_horizontal_review(self):
        points = [dict(p) for p in VALID]
        for point in points:
            point["sigma_hz_m"] = None
            point["sigma_lon_m"] = 0.015
            point["sigma_lat_m"] = 0.020
        result = review_topcon_perimeter(points)
        self.assertTrue(result["ready_for_ods"], result["errors"])
        self.assertAlmostEqual(result["vertices"][0]["sigma_hz_m"], 0.025)

    def test_missing_point_sigmas_does_not_fallback_to_vector_rms(self):
        points = [dict(p) for p in VALID]
        for point in points:
            point["sigma_hz_m"] = None
            point["horizontal_rms_m"] = 0.002
            point["sigma_lon_m"] = None
            point["sigma_lat_m"] = None
        result = review_topcon_perimeter(points)
        self.assertFalse(result["ready_for_ods"])
        self.assertTrue(result["ready_for_geometry"])
        self.assertEqual(len(result["missing_sigmas"]), 3)

    def test_control_point_rejected(self):
        points = [dict(p) for p in VALID]
        points[0]["point_role"] = "CONTROL"
        result = review_topcon_perimeter(points)
        self.assertFalse(result["ready_for_ods"])
        self.assertTrue(any("controle" in e for e in result["errors"]))

    def test_unconfirmed_height_cannot_use_elevation(self):
        points = [dict(p) for p in VALID]
        points[0]["ellipsoidal_height_m"] = None
        result = review_topcon_perimeter(points)
        self.assertFalse(result["ready_for_ods"])
        self.assertTrue(any("altura elipsoidal" in e for e in result["ods_errors"]))

    def test_duplicate_code_rejected(self):
        points = [dict(p) for p in VALID]
        points[1]["sigef_vertex_code"] = points[0]["sigef_vertex_code"]
        result = review_topcon_perimeter(points)
        self.assertFalse(result["ready_for_ods"])
        self.assertTrue(any("repetidos" in e for e in result["ods_errors"]))

    def test_reversed_order_rejected(self):
        result = review_topcon_perimeter([VALID[0], VALID[2], VALID[1]])
        self.assertFalse(result["ready_for_ods"])
        self.assertTrue(any("horário" in e for e in result["ods_errors"]))

    def test_confrontant_required(self):
        points = [dict(p) for p in VALID]
        points[1]["confrontant"] = ""
        result = review_topcon_perimeter(points)
        self.assertFalse(result["ready_for_ods"])
        self.assertTrue(any("confrontante" in e for e in result["ods_errors"]))


if __name__ == "__main__":
    unittest.main()
