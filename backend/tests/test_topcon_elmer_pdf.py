"""Regressão: relatório TOPCON Elmer com M−XXXX em PDF textual.

Dados representativos das linhas Point Summary fornecidas pelo usuário.
O arquivo privado não é incluído no repositório.
"""
import unittest
from unittest.mock import patch

from app.services.topcon_import import _canonical_point_id, _native_point_cells, _native_topcon_tables, parse_topcon_report

ELMER_TEXT = """
Project name: PROCESSAMENTO.ttp
Projection: UTMNorth-Zone_22 : 54W to 48W
Datum: SIRGAS
                                  Point Summary
Nome Código Malha Norte (m) Malha Este (m) Elevação (m) Latitude WGS84 Longitude WGS84 Alt Elip WGS84 (m)
Base       24719,545     459208,404     -6,339   0°13'25,10709223"N   51°21'59,70252673"W  -6,339
M−0223     23908,672     458339,789     -2,414   0°12'58,69655918"N   51°22'27,80315742"W  -2,414
M−0227     25239,509     458398,155     98,767   0°13'42,04145525"N   51°22'25,91601458"W   98,767
M−0298     24400,957     459537,275     -11,576  0°13'14,73103785"N   51°21'49,06267854"W -11,576
M−0299     25478,379     458970,504     -9,647   0°13'49,82185818"N   51°22'07,39964820"W -9,647
                                Observações GPS
Ajustamento
"""

class TestElmerPdfPoints(unittest.TestCase):
    def test_minus_sign_normalization_only_in_identifiers(self):
        self.assertEqual(_canonical_point_id("M−0223"), "M-0223")
        self.assertEqual(_canonical_point_id("M–0227"), "M-0227")

    def test_pdf_colapsa_espaco_entre_longitude_e_altura(self):
        # Neste layout, há um único espaço entre o W e a altitude negativa.
        line = next(line for line in ELMER_TEXT.splitlines() if line.strip().startswith("M−0298"))
        cells = _native_point_cells(line)
        self.assertEqual(len(cells), 7)
        self.assertEqual(cells[5], '51°21\'49,06267854"W')
        self.assertEqual(cells[6], "-11,576")

    def test_five_point_summary_rows_including_four_marcos(self):
        native = _native_topcon_tables(ELMER_TEXT)
        self.assertIsNotNone(native)
        self.assertEqual(set(native["points"]), {
            "Base", "M-0223", "M-0227", "M-0298", "M-0299",
        })
        self.assertEqual(native["points"]["M-0227"]["elevation"], 98.767)
        self.assertEqual(native["points"]["M-0298"]["elevation"], -11.576)

    def test_complete_import_retains_controls_and_marcos(self):
        with patch("app.services.topcon_import._text", return_value=ELMER_TEXT):
            data = parse_topcon_report(b"fixture-data", "ELMER.pdf")
        self.assertEqual(data["point_count"], 5)
        self.assertEqual([p["name"] for p in data["points"]], [
            "Base", "M-0223", "M-0227", "M-0298", "M-0299",
        ])
        self.assertEqual(data["points"][0]["point_role"], "CONTROL")
        self.assertTrue(all(p["point_role"] == "UNCLASSIFIED" for p in data["points"][1:]))
        self.assertTrue(all(p["sigma_e_m"] is None for p in data["points"]))
        self.assertFalse(data["ready_for_sigef"])

if __name__ == "__main__":
    unittest.main()
