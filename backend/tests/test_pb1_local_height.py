import unittest
from app.services.pb1_local_height import fit_local_height,estimate_local_height

class PB1LocalHeightTests(unittest.TestCase):
    def setUp(self):
        self.rows=[
            dict(name=str(i),longitude=lon,latitude=lat,h_gnss_m=z+c,mdt_m=z)
            for i,(lon,lat,z,c) in enumerate([
                (-51.4,.2,20.,-24.),(-51.4,.21,30.,-22.),
                (-51.39,.21,10.,-23.),(-51.39,.2,9.,-22.)])]
    def test_fit_and_prediction(self):
        m=fit_local_height(self.rows)
        self.assertAlmostEqual(m["offset_m"],-22.75)
        r=estimate_local_height(dict(source_value_m=12.,longitude=-51.395,latitude=.205,
                                      pending_reasons=[]),m,[-23.38,.05])
        self.assertAlmostEqual(r["h_ellipsoidal_m"],-10.75)
        self.assertAlmostEqual(r["normal_height_m"],12.63)
        self.assertIsNone(r["sigma_h_m"])
        self.assertEqual(r["status"],"LOCAL_ESTIMATE_UNVALIDATED")
        self.assertFalse(r["outside_control_hull"])
    def test_insufficient_controls(self):
        with self.assertRaises(ValueError):
            fit_local_height(self.rows[:3])
    def test_extrapolation(self):
        m=fit_local_height(self.rows)
        self.assertTrue(estimate_local_height(dict(source_value_m=12.,longitude=-51.38,latitude=.205),m)["outside_control_hull"])
