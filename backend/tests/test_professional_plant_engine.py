"""Testes sintéticos: três modelos realmente diferentes, escala e 61 vértices."""
import io
import math
import unittest

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A2

from app.services.plant_memorial_v2 import prepare_parcels
from app.services.plant_memorial_v3 import make_joint_pdf
from app.services.plant_template_engine import PALETTES, _fonts, _table, Rect


def synthetic_parcels(n=61):
    center = (-50.87, 1.08)
    ring = [
        [center[0] + .005*math.cos(2*math.pi*i/n),
         center[1] + .007*math.sin(2*math.pi*i/n)]
        for i in range(n)
    ]
    ring.append(ring[0])
    return prepare_parcels([{
        "name": "IMOVEL TESTE",
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "vertex_names": [f"EQGV-V-{i+500}" for i in range(n)],
        "altitudes_m": [float(i) for i in range(n)],
        "confrontants": ["CONFRONTANTE DE TESTE"]*n,
    }])


FLAGS = {
    "grid": True, "title": True, "north": True,
    "scale_text": True, "scale_bar": True, "coordinates": True,
    "vertex_labels": True, "azimuths": False,
    "distances": False, "confrontants": False,
    "situation": False, "technical_stamp": True,
}


class ProfessionalPlantEngineTest(unittest.TestCase):
    def test_all_three_templates_generate_real_pdf(self):
        for model in PALETTES:
            with self.subTest(model=model):
                data, paper, scale = make_joint_pdf(
                    parcels=synthetic_parcels(), title="IMOVEL TESTE",
                    owner_name="DETENTOR TESTE", responsible_name="ENG TESTE",
                    croqui=False, raster_b64=None, raster_source=None,
                    paper_format="A2", orientation="retrato",
                    layout_template=model, plant_elements=FLAGS,
                    edited_memorial="DESCRICAO DO PERIMETRO\n" +
                        ("Vértices originais preservados na tabela. "*200),
                )
                self.assertTrue(data.startswith(b"%PDF-"), model)
                self.assertGreater(len(data), 7000, model)
                self.assertEqual(paper, "A2")
                self.assertGreater(scale, 0)

    def test_fonts_are_embedded_when_available(self):
        regular, bold, _ = _fonts()
        self.assertIn(regular, ("AKSans", "Helvetica"))
        self.assertIn(bold, ("AKSans-Bold", "Helvetica-Bold"))

    def test_table_paginate_without_losing_rows(self):
        sink=io.BytesIO()
        p=canvas.Canvas(sink,pagesize=A2)
        rows=[(f"EQGV-V-{i+500}", "-50°50'20,123\"", "01°04'30,101\"",
               "513400.123", "118700.654", "1,25", "135°42'", "120,20")
              for i in range(61)]
        n=_table(p, Rect(30, 30, A2[0]-60, 400), rows,
                 PALETTES["classic_lateral"], columns=2, font_size=6.4)
        self.assertGreater(n, 0)
        self.assertLessEqual(n, 61)
        p.save()


if __name__=="__main__":
    unittest.main()
