import unittest
from app.services.plant_memorial_v2 import Parcel, _display_altitude
from app.services.plant_memorial_v3 import _columns

class DualAltitudeTests(unittest.TestCase):
    def parcel(self, h, hn, name="TEST-M-0001"):
        return Parcel(name="Teste", points=[(-51,0.2)], names=[name],
            area_ha=1, perimeter=100, segments=[], confrontants=[""],
            altitudes=[h], normal_altitudes=[hn])

    def test_both_heights(self):
        text = _display_altitude(self.parcel(-2.414,21.186),0)
        self.assertIn("Altitude geométrica (h)",text)
        self.assertIn("Altitude normal (HN)",text)
        self.assertIn("-2,41",text)
        self.assertIn("21,19",text)

    def test_missing_height_not_zero(self):
        text = _display_altitude(self.parcel(None,13.575,"TEST-V-0001"),0)
        self.assertNotIn("Altitude geométrica",text)
        self.assertIn("HN estimada",text)

    def test_zero_valid(self):
        self.assertIn("0,00",_display_altitude(self.parcel(0,None),0))

    def test_table_nine_columns(self):
        columns = _columns(900)
        self.assertEqual(len(columns),9)
        self.assertAlmostEqual(sum(w for _,w in columns),900)
