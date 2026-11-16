"""Regressão: quadro cartográfico sempre usa HN, nunca a h GNSS."""
import unittest
from io import BytesIO
from pypdf import PdfReader
from app.services.plant_memorial_v3 import make_joint_pdf
from pyproj import Transformer
from app.services.plant_memorial_v2 import prepare_parcels
from app.services.plant_template_engine import _rows


class TestPs4PdfNormalAltitudes(unittest.TestCase):
    def test_normal_altitudes_match_memorial_and_mark_estimated_v(self):
        original = [-17.70, None, None, -20.88]
        hn = [5.86, 5.59, 5.40, 2.64]
        raw = [{
            "name": "Teste M-V-M",
            "geometry": {"type": "Polygon", "coordinates": [[
                [-50.876, 0.407], [-50.875, 0.407],
                [-50.874, 0.406], [-50.873, 0.404],
                [-50.876, 0.407],
            ]]},
            "vertex_names": ["CPBR-M-578", "VIRTUAL-V-0001",
                             "VIRTUAL-V-0002", "CPBR-M-581"],
            "altitudes_m": original,
            "normal_altitudes_m": hn,
        }]
        parcel = prepare_parcels(raw)
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:32622",
                                           always_xy=True)
        rows = _rows(parcel, transformer)
        self.assertEqual(len(rows), 4)
        self.assertEqual([row[5] for row in rows],
                         ["5,86", "5,59~", "5,40~", "2,64"])
        self.assertNotIn("-17,70", str(rows))
        self.assertNotIn("-20,88", str(rows))

    def test_all_thirteen_vertices_from_homologation_pdf(self):
        # Coordenadas e HN do PDF de teste fornecido pelo operador.
        # Os valores HN dos V são PROVISÓRIOS e interpolados, não medidos.
        names = ["CPBR-M-578"] + [
            f"VIRTUAL-V-{index:04d}" for index in range(1, 9)
        ] + ["CPBR-M-581", "CPBR-M-582", "CPBR-M-583", "CPBR-M-584"]
        coords = [
            (-50.8745633, .4086214),
            (-50.8740642, .4076772), (-50.8733253, .4078514),
            (-50.8728014, .4073633), (-50.8727561, .4063869),
            (-50.8718300, .4058175), (-50.8713119, .4049569),
            (-50.8710011, .4033917), (-50.8716178, .4015069),
            (-50.8703600, .3979300), (-50.8753689, .4011942),
            (-50.8857139, .4003225), (-50.8867964, .4042342),
        ]
        hn = [5.86, 5.59, 5.40, 5.22, 4.98, 4.71, 4.46,
              4.07, 3.58, 2.64, 5.40, 1.43, 2.71]
        h = [-17.70] + [None] * 8 + [-20.88, -18.12, -22.07, -20.80]
        parcel = prepare_parcels([{
            "name": "Recorte técnico preliminar",
            "geometry": {"type": "Polygon",
                         "coordinates": [list(map(list, coords + [coords[0]]))]},
            "vertex_names": names,
            "normal_altitudes_m": hn,
            "altitudes_m": h,
        }])
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:32622",
                                           always_xy=True)
        actual = _rows(parcel, transformer)
        self.assertEqual(len(actual), 13)
        self.assertEqual(
            [row[5] for row in actual],
            [f"{value:.2f}".replace(".", ",") + ("~" if 1 <= index <= 8 else "")
             for index, value in enumerate(hn)],
        )
        self.assertTrue(all("-" not in row[5] for row in actual))

    def test_pdf_moderno_memorial_e_quadro_nao_imprimem_h_elipsoidal(self):
        parcel = prepare_parcels([{
            "name": "Teste HN PDF",
            "geometry": {"type": "Polygon", "coordinates": [[
                [-50.876, 0.407], [-50.875, 0.407],
                [-50.875, 0.406], [-50.876, 0.406],
                [-50.876, 0.407],
            ]]},
            "vertex_names": ["CPBR-M-578", "VIRTUAL-V-0001",
                             "VIRTUAL-V-0002", "CPBR-M-581"],
            "altitudes_m": [-17.70, None, None, -20.88],
            "normal_altitudes_m": [5.86, 5.59, 5.40, 2.64],
        }])
        pdf, _paper, _scale = make_joint_pdf(
            parcels=parcel, title="Teste HN GEO90",
            owner_name="Homologacao", responsible_name="Teste tecnico",
            croqui=False, raster_b64=None, raster_source=None,
            paper_format="A2", layout_template="cartographic_frame",
            plant_elements={"situation": False},
        )
        content = "\n".join(page.extract_text() or ""
                            for page in PdfReader(BytesIO(pdf)).pages)
        self.assertIn("QUADRO DE COORDENADAS E SEGMENTOS", content)
        self.assertIn("HN (m)", content)
        for value in ("5,86", "5,59~", "5,40~", "2,64"):
            self.assertIn(value, content)
        for wrong in ("-17,70", "-20,88"):
            self.assertNotIn(wrong, content)

    def test_missing_normal_is_not_replaced_by_ellipsoidal_height(self):
        raw = [{
            "name": "Sem HN",
            "geometry": {"type": "Polygon", "coordinates": [[
                [-50.876, 0.407], [-50.875, 0.406],
                [-50.874, 0.404], [-50.876, 0.407]
            ]]},
            "vertex_names": ["M-1", "VIRTUAL-V-0001", "M-2"],
            "altitudes_m": [-22.0, None, -18.0],
            "normal_altitudes_m": [None, None, None],
        }]
        parcel = prepare_parcels(raw)
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:32622",
                                           always_xy=True)
        rows = _rows(parcel, transformer)
        self.assertEqual([row[5] for row in rows], ["—", "—", "—"])


if __name__ == "__main__":
    unittest.main()
