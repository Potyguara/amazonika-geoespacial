"""Regressões cartográficas para refinamento de três layouts profissionais."""
import io
import math
import unittest

from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.pagesizes import A2

from app.services.plant_template_engine import (
    Rect, PALETTES, _table, _table_height, _pt_meter,
)


def synthetic_rows(n):
    return [
        (
            f"EQGV-V-{500+i}", '-50°52\'40,069"', '01°05\'20,821"',
            f"{513000+i*3:.3f}", f"{120000+i*3:.3f}",
            "1,25", "117°42'", "47,59",
        )
        for i in range(n)
    ]


class ProfessionalRefinementTests(unittest.TestCase):
    def test_dense_table_uses_exact_height_without_dead_space(self):
        h = _table_height(61, 2, font_size=7.0)
        self.assertGreater(h, 350)
        self.assertLess(h, 460)

    def test_two_columns_do_not_duplicate_or_skip_rows(self):
        output = io.BytesIO()
        pdf = Canvas(output, pagesize=A2)
        rows = synthetic_rows(61)
        visible = _table(
            pdf, Rect(33, 54, A2[0]-66, 335),
            rows, PALETTES["classic_lateral"], columns=2, font_size=7.0,
        )
        self.assertGreater(visible, 20)
        self.assertLess(visible, 61)
        pdf.save()
        self.assertTrue(output.getvalue().startswith(b"%PDF-"))

    def test_geometric_scale_is_points_per_meter(self):
        self.assertAlmostEqual(_pt_meter(1000) * 1000, 72/.0254, places=6)

    def test_empty_table_has_no_fictitious_vertices(self):
        output = io.BytesIO()
        pdf = Canvas(output, pagesize=A2)
        visible = _table(
            pdf, Rect(33, 54, A2[0]-66, 140),
            [], PALETTES["modern_lateral"], columns=2, font_size=7.0,
        )
        self.assertEqual(visible, 0)
        pdf.save()


if __name__ == "__main__":
    unittest.main()
