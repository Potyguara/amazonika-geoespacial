"""Testes de identificação de folhas, sem banco e sem imagens grandes."""
import json
import tempfile
import unittest
from pathlib import Path
from shapely.geometry import box, mapping
from app.services.pb1_articulation import identify_pb1_sheets


class Pb1ArticulationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "articulacao.geojson"
        self.path.write_text(json.dumps({
            "type": "FeatureCollection", "features": [
                {"type": "Feature", "properties": {
                    "INOM": "NA-22-Y-B-III-1-NO",
                    "MI_1": "0121-1-NO", "Blocos": "Bloco 4"
                }, "geometry": mapping(box(-51.5, 1.875, -51.375, 2.0))},
                {"type": "Feature", "properties": {
                    "INOM": "NA-22-Y-B-III-1-NE",
                    "MI_1": "0121-1-NE", "Blocos": "Bloco 4"
                }, "geometry": mapping(box(-51.375, 1.875, -51.25, 2.0))},
            ],
        }), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_um_imovel_localiza_folha_e_mi(self):
        result = identify_pb1_sheets(mapping(box(-51.46, 1.9, -51.40, 1.95)), str(self.path))
        self.assertEqual(result["sheet_count"], 1)
        self.assertEqual(result["matched_sheets"][0]["mi"], "0121-1-NO")
        self.assertEqual(result["accuracy_status"], "NOT_VERIFIED")

    def test_imovel_cruza_duas_folhas(self):
        result = identify_pb1_sheets(mapping(box(-51.4, 1.9, -51.35, 1.95)), str(self.path))
        self.assertEqual(result["sheet_count"], 2)
        self.assertTrue(all(p["area_overlap"] for p in result["matched_sheets"]))

    def test_borda_contigua_e_informada(self):
        result = identify_pb1_sheets(mapping(box(-51.45, 1.90, -51.375, 1.95)), str(self.path))
        self.assertEqual(result["sheet_count"], 2)
        by_inom = {item["inom"]: item for item in result["matched_sheets"]}
        touching = by_inom["NA-22-Y-B-III-1-NE"]
        overlapping = by_inom["NA-22-Y-B-III-1-NO"]
        self.assertTrue(touching["boundary_touch_only"])
        self.assertFalse(touching["area_overlap"])
        self.assertTrue(overlapping["area_overlap"])
        self.assertFalse(overlapping["boundary_touch_only"])

    def test_sem_folha_retorna_vazio(self):
        result = identify_pb1_sheets(mapping(box(-52, -1, -51.9, -0.9)), str(self.path))
        self.assertEqual(result["sheet_count"], 0)

    def test_rejeita_geometria_nao_poligonal(self):
        with self.assertRaisesRegex(ValueError, "polígono"):
            identify_pb1_sheets({"type": "Point", "coordinates": [-51.4, 1.9]}, str(self.path))


if __name__ == "__main__":
    unittest.main()
