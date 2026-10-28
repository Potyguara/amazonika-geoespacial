"""Regressão: memorial conjunto de cinco matrículas SIGEF com coordenadas XYZ."""
import unittest
from app.services.plant_memorial_v2 import prepare_parcels, build_joint_memorial


class MultiParcelXYZTests(unittest.TestCase):
    def test_five_adjacent_xyz_parcels(self):
        parcels = []
        for index in range(5):
            x0 = -51.0 + index * .001
            ring = [
                [x0, -.03, 35.0], [x0+.001, -.03, 36.0],
                [x0+.001, -.029, 37.0], [x0, -.029, 38.0],
                [x0, -.03, 35.0],
            ]
            parcels.append({
                "name": f"Imóvel {index+1}",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "vertex_names": [f"POL-{index+1}-V0{i}" for i in range(1,5)],
                "confrontants": ["Maria Trindade"] * 4,
            })
        prepared = prepare_parcels(parcels)
        self.assertEqual(len(prepared), 5)
        self.assertEqual(sum(len(p.points) for p in prepared), 20)
        self.assertTrue(all(len(vertex) == 2 for p in prepared for vertex in p.points))
        text = build_joint_memorial(
            prepared, title="Cinco imóveis",
            owner="Requerente", responsible="Responsável técnico", croqui=False)
        for n in range(1, 6):
            self.assertIn(f"DESCRIÇÃO DO PERÍMETRO - Imóvel {n}", text)
        self.assertIn("Maria Trindade", text)
        self.assertIn("ÁREA TOTAL", text)

if __name__ == "__main__":
    unittest.main()
