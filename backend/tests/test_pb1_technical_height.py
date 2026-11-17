import unittest
from app.services.pb1_vertical import PB1VerticalPoint, convert_pb1_height

class PB1TechnicalHeightTests(unittest.TestCase):
    def test_normal_signed_factor(self):
        point = PB1VerticalPoint(vertex_id="V1", source_value_m=13.575,
            source_vertical_kind="NORMAL", source_vertical_datum="Santana",
            conversion_model="HGEOHNOR2020", conversion_factor_m=-20,
            source_sigma_m=2, factor_sigma_m=.2, raster_sha256="a"*64)
        result = convert_pb1_height(point)
        self.assertAlmostEqual(result["h_ellipsoidal_m"], -6.425)
        self.assertAlmostEqual(result["sigma_h_m"], 2.01, places=3)
        self.assertEqual(result["status"], "PRELIMINARY_RT_REVIEW")

    def test_ellipsoidal_source_sigma_preserved(self):
        point = PB1VerticalPoint(vertex_id="V1", source_value_m=13.575,
            source_vertical_kind="ELLIPSOIDAL", source_vertical_datum="SIRGAS2000",
            source_sigma_m=2, raster_sha256="a"*64)
        result = convert_pb1_height(point)
        self.assertEqual(result["h_ellipsoidal_m"], 13.575)
        self.assertEqual(result["sigma_h_m"], 2)
