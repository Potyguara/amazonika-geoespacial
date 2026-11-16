import unittest
from pydantic import ValidationError
from app.services.pb1_vertical import PB1VerticalPoint, convert_pb1_height

BASE = {
    "vertex_id": "ABC-V-0001",
    "source_value_m": 139.83609,
    "source_vertical_datum": "Datum vertical informado pelo produtor",
    "raster_sha256": "a" * 64,
}

class Pb1VerticalTests(unittest.TestCase):
    def test_normal_hgeohnor_inverte_para_h(self):
        p = PB1VerticalPoint(**BASE, source_vertical_kind="NORMAL",
            conversion_model="HGEOHNOR2020", conversion_factor_m=-8.125,
            source_sigma_m=1.2, factor_sigma_m=0.3)
        r = convert_pb1_height(p)
        self.assertAlmostEqual(r["h_ellipsoidal_m"], 131.7111, places=4)
        self.assertAlmostEqual(r["sigma_h_m"], (1.2**2+0.3**2)**0.5, places=4)

    def test_ortometrica_mapgeo(self):
        p = PB1VerticalPoint(**BASE, source_vertical_kind="ORTHOMETRIC",
            conversion_model="MAPGEO2015", conversion_factor_m=9.3)
        r = convert_pb1_height(p)
        self.assertEqual(r["sigma_h_m"], None)
        self.assertAlmostEqual(r["h_ellipsoidal_m"], 149.1361, places=4)

    def test_nao_converter_sem_datum_vertical(self):
        with self.assertRaises(ValidationError):
            PB1VerticalPoint(**BASE, source_vertical_kind="UNKNOWN")

    def test_nao_usar_mapgeo_para_altitude_normal(self):
        with self.assertRaises(ValidationError):
            PB1VerticalPoint(**BASE, source_vertical_kind="NORMAL",
                conversion_model="MAPGEO2015", conversion_factor_m=9.3)

    def test_nao_inventar_fator(self):
        with self.assertRaises(ValidationError):
            PB1VerticalPoint(**BASE, source_vertical_kind="NORMAL",
                conversion_model="HGEOHNOR2020")

if __name__ == "__main__":
    unittest.main()
