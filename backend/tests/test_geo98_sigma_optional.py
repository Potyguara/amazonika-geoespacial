"""GEO98 - fechamento do perímetro GNSS sem exigir sigmas editados."""
import unittest
from app.services.topcon_perimeter_review import review_topcon_perimeter

class Geo98SigmaOptionalTest(unittest.TestCase):
    def test_geometry_passes_without_point_axis_sigmas(self):
        coordinates = [(-51.0, .45), (-50.99, .44), (-51.0, .43)]
        points = [{
            "name":f"M{i+1}","sigef_vertex_code":f"ABCD-M-{i+1:04d}",
            "point_role":"BOUNDARY", "longitude":lon,"latitude":lat,
            "sigef_method":"PG1","boundary_type":"LA6",
            "confrontant":"Vizinho","ellipsoidal_height_m":10.0,
            "sigma_hz_m":None,"sigma_lon_m":None,"sigma_lat_m":None,
            "sigma_h_m":None,
        } for i,(lon,lat) in enumerate(coordinates)]
        out=review_topcon_perimeter(points)
        self.assertTrue(out["ready_for_geometry"],out["errors"])
        self.assertFalse(out["ready_for_ods"])
        self.assertEqual(len(out["missing_sigmas"]),3)
        self.assertIsNotNone(out["geometry"])

if __name__=="__main__":
    unittest.main()
