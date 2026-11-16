"""GEO99: Memorial prioriza HN sem substituir h SIGEF."""
import unittest
from app.services.plant_memorial_v2 import prepare_parcels, build_joint_memorial

class Geo99NormalAltitudeTest(unittest.TestCase):
    def test_memorial_distinguishes_measured_m_and_interpolated_v(self):
        parcels=prepare_parcels([{
            "name":"Teste",
            "geometry":{"type":"Polygon","coordinates":[[
                [-51.0,.45],[-50.99,.44],[-51.0,.43],[-51.0,.45]
            ]]},
            "vertex_names":["CPBR-M-0001","CPBR-V-0002","CPBR-M-0003"],
            "confrontants":["Confrontante"]*3,
            "altitudes_m":[-17.0,None,-20.0],
            "normal_altitudes_m":[5.0,4.5,4.0],
        }])
        text=build_joint_memorial(
            parcels,title="Teste",owner="Teste",responsible="Teste",croqui=False
        )
        self.assertIn("Altitude normal (HN): 5,00 m",text)
        self.assertIn("HN estimada (interpolação M–V–M): 4,50 m",text)
        self.assertNotIn("Altitude: -17,00",text)

if __name__=="__main__":
    unittest.main()
