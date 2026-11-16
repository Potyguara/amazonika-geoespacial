"""GEO99: nenhum campo avançado é exigido para geometria preliminar."""
import unittest
from app.services.topcon_perimeter_review import review_topcon_perimeter

class Geo99OptionalAttributesTest(unittest.TestCase):
    def test_geometry_independent_of_sigmas_confrontants_and_heights(self):
        coordinates=[(-51.0,.45),(-50.99,.44),(-51.0,.43)]
        points=[{
            "name":f"M{i+1}","sigef_vertex_code":f"CPBR-M-{i+1:04d}",
            "point_role":"BOUNDARY","longitude":lon,"latitude":lat,
            "sigef_method":"","boundary_type":"","confrontant":"",
            "ellipsoidal_height_m":None,
            "sigma_hz_m":None,"sigma_lon_m":None,"sigma_lat_m":None,
            "sigma_h_m":None,
        } for i,(lon,lat) in enumerate(coordinates)]
        result=review_topcon_perimeter(points)
        self.assertTrue(result["ready_for_geometry"],result["errors"])
        self.assertFalse(result["ready_for_ods"])
        self.assertIsNotNone(result["geometry"])
        self.assertTrue(result["ods_errors"])
        self.assertEqual(result["missing_sigmas"],[p["sigef_vertex_code"] for p in points])

if __name__=="__main__":
    unittest.main()
