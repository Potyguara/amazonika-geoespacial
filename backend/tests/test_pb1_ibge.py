import unittest
from app.services.pb1_ibge import parse_ibge_output

class PB1IbgeTests(unittest.TestCase):
    points = [{"name":"V1","latitude":0.23,"longitude":-51.36},
              {"name":"V2","latitude":0.22,"longitude":-51.35}]
    raw = "V1 0.23000000 -51.36000000 -20.1 0.2 Santana\nV2 0.22000000 -51.35000000 -20.2 0.3 Santana"
    def test_import(self):
        self.assertEqual(parse_ibge_output(self.raw,self.points)["V1"],[-20.1,0.2])
    def test_missing(self):
        with self.assertRaises(ValueError):
            parse_ibge_output(self.raw.splitlines()[0],self.points)
    def test_duplicate(self):
        with self.assertRaises(ValueError):
            parse_ibge_output(self.raw+"\n"+self.raw.splitlines()[0],self.points)
    def test_coordinate_mismatch(self):
        with self.assertRaises(ValueError):
            parse_ibge_output(self.raw.replace("-51.36000000","-51.35000000"),self.points)
    def test_invalid_sigma(self):
        with self.assertRaises(ValueError):
            parse_ibge_output(self.raw.replace("0.2 Santana","-0.2 Santana"),self.points)
