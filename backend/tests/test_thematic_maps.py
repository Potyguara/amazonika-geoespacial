"""Contract and render tests for thematic maps."""
import unittest
from shapely.geometry import Polygon, LineString, Point
from app.services.thematic_maps import Layer, TEMPLATES, render_thematic_pdf


class ThematicTests(unittest.TestCase):
    def test_ten_templates_plus_custom(self):
        self.assertEqual(len(TEMPLATES), 11)

    def test_pdf_multi_layer(self):
        property_geom = Polygon([(-51.1,-.06),(-51.09,-.06),(-51.09,-.05),(-51.1,-.05)])
        layers = [
            Layer("Propriedade", "SIGEF", property_geom, "#d51f1f", "property"),
            Layer("Rio", "IBGE", LineString([(-51.11,-.055),(-51.08,-.055)]), "#146cbb", "theme"),
            Layer("Nascente", "Amazônika", Point(-51.095,-.055), "#1285c7", "theme"),
        ]
        output = render_thematic_pdf("Hidrografia", "Amapá", layers, "IBGE")
        self.assertTrue(output.startswith(b"%PDF"))
        self.assertGreater(len(output), 2000)

    def test_requires_property(self):
        with self.assertRaisesRegex(ValueError,"propriedade"):
            render_thematic_pdf("Teste","",[
                Layer("Rio","IBGE",LineString([(-51,0),(-51.01,0)]),"#146cbb","theme")],"")
