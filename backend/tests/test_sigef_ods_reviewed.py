"""Integração exportação ODS com o modelo SIGEF real instalado no repositório."""
import io
import unittest
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from app.services.sigef_ods_reviewed import build_reviewed_sigef_ods
from app.services.technical_import import parse_sigef_ods
from app.services.sigef_ods import _template_path, TABLE


def vertex(name, lon, lat):
    return {
        "name": name,
        "point_role": "BOUNDARY",
        "sigef_vertex_code": name,
        "longitude": lon, "latitude": lat,
        "ellipsoidal_height_m": -2.1,
        "sigma_hz_m": 0.018,
        "sigma_lon_m": 0.01, "sigma_lat_m": 0.01, "sigma_h_m": 0.025,
        "sigef_method": "PG1", "boundary_type": "LA6",
        "confrontant": "CONFRONTANTE INFORMADO",
        "confrontant_cns": "", "confrontant_registration": "",
    }


def payload():
    return {
        "identification": {
            "holder_name": "TITULAR TESTE",
            "holder_document": "12345678901",
            "property_name": "FAZENDA TESTE",
            "situation": "Área não Titulada",
            "municipalities": ["Macapá-AP", "Santana-AP"],
        },
        "parcels": [
            {"number": "1", "name": "LOTE A", "vertices": [
                vertex("TEST-M-0001", -51.4, 0.4),
                vertex("TEST-M-0002", -51.39, 0.39),
                vertex("TEST-M-0003", -51.41, 0.39),
            ]},
            {"number": "2", "name": "LOTE B", "vertices": [
                vertex("TEST-M-0004", -51.38, 0.4),
                vertex("TEST-M-0005", -51.37, 0.39),
                vertex("TEST-M-0006", -51.39, 0.39),
            ]},
        ],
        "neighbors": [],
    }


class ReviewedSigefOdsTests(unittest.TestCase):
    def test_multi_sheet_roundtrip(self):
        if not _template_path().is_file():
            self.skipTest("Modelo SIGEF não está disponível.")
        blob = build_reviewed_sigef_ods(payload())
        with ZipFile(io.BytesIO(blob)) as z:
            self.assertEqual(z.namelist()[0], "mimetype")
            self.assertEqual(z.getinfo("mimetype").compress_type, 0)
            root = ET.fromstring(z.read("content.xml"))
            names = [
                t.get(TABLE + "name") for t in root.iter(TABLE + "table")
            ]
            self.assertIn("identificacao", names)
            self.assertIn("perimetro_1", names)
            self.assertIn("perimetro_2", names)
            # Modelo ODS oficial pode repetir a linha modelo N vezes:
            # cada vertice exportado deve representar uma unica linha.
            for name in ("perimetro_1", "perimetro_2"):
                tab = next(t for t in root.iter(TABLE + "table")
                           if t.get(TABLE + "name") == name)
                vertex_rows = tab.findall(TABLE + "table-row")[11:14]
                self.assertEqual(len(vertex_rows), 3)
                for row in vertex_rows:
                    self.assertNotIn(TABLE + "number-rows-repeated", row.attrib)
        parsed = parse_sigef_ods(blob)
        self.assertEqual(len(parsed["features"]), 2)
        self.assertEqual(parsed["vertex_count"], 6)
        self.assertEqual(parsed["features"][0]["properties"]["vertexNames"][0], "TEST-M-0001")
        self.assertEqual(parsed["features"][1]["properties"]["vertexNames"][0], "TEST-M-0004")
        self.assertAlmostEqual(
            parsed["features"][0]["properties"]["sigef_vertex_details"][0]["altitude_m"],
            -2.1,
        )

    def test_blocks_missing_height_and_sigma(self):
        case = payload()
        case["parcels"][0]["vertices"][0]["sigma_lon_m"] = None
        with self.assertRaisesRegex(ValueError, "sigma longitude"):
            build_reviewed_sigef_ods(case)

    def test_blocks_internal_overlap(self):
        case = payload()
        case["parcels"][1]["vertices"] = [
            vertex("TEST-M-0004", -51.4, 0.4),
            vertex("TEST-M-0005", -51.39, 0.39),
            vertex("TEST-M-0006", -51.41, 0.39),
        ]
        with self.assertRaisesRegex(ValueError, "sobrepõem"):
            build_reviewed_sigef_ods(case)


if __name__ == "__main__":
    unittest.main()
