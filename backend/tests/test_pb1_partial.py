import unittest
from app.services.pb1_partial import partial_parameters, partial_vertex

class PartialTests(unittest.TestCase):
    def test_pec_estimated_not_verified(self):
        p=partial_parameters({"pec":"PEC A","scale":"25000"},{})
        self.assertAlmostEqual(p["horizontal_sigma_m"],7.5)
        self.assertEqual(p["sigma_origin"],"PEC_REFERENCE_ISOTROPIC_ESTIMATE")
        self.assertIsNone(p["source_sigma_m"])
    def test_missing(self):
        p=partial_parameters({}, {})
        self.assertIsNone(p["horizontal_sigma_m"])
    def test_unknown_vertical(self):
        r=partial_vertex({"name":"V1","latitude":0.2,"longitude":-51},13.575,partial_parameters({},{}),[-23.38,.05],{})
        self.assertIsNone(r["h_ellipsoidal_m"])
        self.assertEqual(r["source_value_m"],13.575)
    def test_declared_normal(self):
        source={"vertical_kind":"NORMAL","vertical_datum":"Santana","source_model":"hgeoHNOR2020","vertical_reference":"Documento de teste"}
        r=partial_vertex({"name":"V1","latitude":0.2,"longitude":-51},13.575,partial_parameters(source,{}),[-23.38,.05],source)
        self.assertAlmostEqual(r["h_ellipsoidal_m"],-9.805)
        self.assertIsNone(r["sigma_h_m"])
