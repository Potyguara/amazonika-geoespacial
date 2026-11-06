"""Smoke tests for print-ready thematic layout and exact vector geometries."""
import unittest
from shapely.geometry import Polygon, LineString
from app.services.thematic_maps import Layer
from app.services.thematic_matplotlib import render_matplotlib

class ThematicMatplotlibTests(unittest.TestCase):
    def setUp(self):
        p=Polygon([(-51.11,.01),(-51.08,.01),(-51.08,.03),(-51.11,.03)])
        west=Polygon([(-51.2,-.01),(-51.09,-.01),(-51.09,.08),(-51.2,.08)])
        east=Polygon([(-51.09,-.01),(-51.0,-.01),(-51.0,.08),(-51.09,.08)])
        self.layers=[
            Layer("Geologia: Barreiras","IBGE",west,"#7dbf73","theme"),
            Layer("Geologia: Alter do Chão","IBGE",east,"#e8bc56","theme"),
            Layer("Hidrografia","IBGE",LineString([(-51.2,.0),(-51.01,.06)]),"#2a79b4","theme"),
            Layer("Propriedade","Cliente",p,"#cf2727","property"),
        ]
    def test_render_pdf_and_png(self):
        for kind,magic in (("pdf",b"%PDF"),("png",b"\\x89PNG")):
            raw=render_matplotlib("Unidades geológicas","",self.layers,
                "IBGE",{"mode":"minimalista","grid":"border","property":"outline"},fmt=kind)
            self.assertTrue(
                raw.startswith(magic),
                f"Formato solicitado={kind}; prefixo retornado={raw[:20]!r}; "
                f"tamanho={len(raw)}; magic esperado={magic!r}",
            )
            self.assertGreater(len(raw),1000)
    def test_disallow_impossible_manual_scale(self):
        with self.assertRaisesRegex(ValueError,"Escala manual"):
            render_matplotlib("Geologia","",self.layers,"IBGE",{"scale":1000})
