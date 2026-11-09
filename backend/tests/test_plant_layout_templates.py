"""Regressões dos modelos de planta e paginação do memorial."""
import math
import unittest

from app.services.plant_memorial_v2 import prepare_parcels
from app.services.plant_memorial_v3 import make_joint_pdf, _layout


def parcel_with_vertices(n=61):
    # Perímetro sintético; não corresponde ao imóvel de homologação.
    cx, cy = -50.87, 1.08
    ring = [
        [cx + .001 * math.cos(2 * math.pi * i / n),
         cy + .001 * math.sin(2 * math.pi * i / n)]
        for i in range(n)
    ]
    ring.append(ring[0])
    return prepare_parcels([{
        "name": "LOTE SINTETICO",
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "vertex_names": [f"TEST-V-{i:03d}" for i in range(n)],
        "confrontants": ["Vizinho teste"] * n,
        "altitudes_m": [float(i) for i in range(n)],
    }])


class TestPlantLayouts(unittest.TestCase):
    def test_bottom_table_spans_available_paper_width(self):
        projected = [[(500000 + i*2, 120000 + i*2) for i in range(61)]]
        _, width, _, side, _, _, bottom, _ = _layout(
            projected, vertex_count=61, paper="A3",
            orientation="paisagem", scale=None,
            show_coordinates=True, layout_template="inferior",
        )
        self.assertAlmostEqual(bottom[2], width - 76)
        self.assertGreater(bottom[2], side - 38)
        self.assertGreater(bottom[3], 0)

    def test_61_vertices_generate_bottom_layout_pdf(self):
        parcels = parcel_with_vertices()
        pdf, page, scale = make_joint_pdf(
            parcels=parcels, title="LOTE SINTETICO",
            owner_name="TESTADOR", responsible_name="RT TESTE",
            croqui=False, raster_b64=None, raster_source=None,
            paper_format="A3", orientation="paisagem",
            layout_template="inferior",
            plant_elements={
                "title": True, "grid": False, "north": False,
                "scale_text": True, "scale_bar": False,
                "vertex_labels": False, "azimuths": False,
                "distances": False, "confrontants": False,
                "coordinates": True, "situation": False,
                "technical_stamp": False,
            },
            edited_memorial="DESCRIÇÃO DO PERÍMETRO\n" +
                ("De um vértice ao próximo, com rumo e confrontação conhecidos. " * 140),
        )
        self.assertEqual(page, "A3")
        self.assertGreater(scale, 0)
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertGreater(len(pdf), 5000)


if __name__ == "__main__":
    unittest.main()
