from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

from app.services.geospatial_export import export_polygon
from app.services.plant_memorial_v2 import prepare_parcels, build_joint_memorial
from app.services.plant_memorial_pro import make_joint_pdf
from app.services.memorial_docx import build_memorial_docx


def square(lon: float, lat: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[
            [lon, lat], [lon + 0.001, lat],
            [lon + 0.001, lat + 0.001], [lon, lat + 0.001],
            [lon, lat],
        ]],
    }


class GeospatialDocumentsTests(unittest.TestCase):
    def setUp(self):
        self.geometry = square(-51.05, 0.05)

    def test_txt_semicolon_and_coordinate_columns(self):
        content, filename, media_type = export_polygon(
            geometry=self.geometry, filename="Quadra 1", format="txt",
            names=["M01", "M02", "M03", "M04"],
        )
        text = content.decode("utf-8-sig")
        rows = text.splitlines()
        self.assertEqual(rows[0], "codigo;X;Y")
        self.assertEqual(len(rows), 5)
        self.assertEqual([row.split(";")[0] for row in rows[1:]], ["M01", "M02", "M03", "M04"])
        for row in rows[1:]:
            self.assertEqual(len(row.split(";")), 3)
            float(row.split(";")[1])
            float(row.split(";")[2])
        self.assertTrue(filename.endswith(".txt"))

    def test_kml_polygon_and_named_vertices(self):
        content, filename, _ = export_polygon(
            geometry=self.geometry, filename="Quadra 1", format="kml",
            names=["M01", "M02", "M03", "M04"],
        )
        self.assertIn(b"<Polygon>", content)
        self.assertIn(b"<name>M01</name>", content)
        self.assertTrue(filename.endswith(".kml"))

    def test_shapefile_zip_with_vertices_and_txt(self):
        content, filename, _ = export_polygon(
            geometry=self.geometry, filename="Quadra 1", format="shp",
        )
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
            for prefix in ["poligono", "vertices"]:
                for suffix in [".shp", ".shx", ".dbf", ".prj"]:
                    self.assertIn(prefix + suffix, names)
            self.assertIn("coordenadas_utm.txt", names)
            self.assertTrue(archive.read("coordenadas_utm.txt").decode("utf-8-sig").startswith("codigo;X;Y\n"))
        self.assertTrue(filename.endswith(".zip"))

    def test_joint_pdf_with_raster_and_sketch_note(self):
        parcels = prepare_parcels([
            {"name": "Lote 01", "geometry": square(-51.05, 0.05), "vertex_names": ["A1", "A2", "A3", "A4"]},
            {"name": "Lote 02", "geometry": square(-51.052, 0.05), "vertex_names": ["B1", "B2", "B3", "B4"]},
        ])
        self.assertEqual(len(parcels), 2)
        self.assertTrue(all(item.area_ha > 0 and item.perimeter > 0 for item in parcels))
        image = Image.new("RGB", (200, 150), "green")
        raster = io.BytesIO()
        image.save(raster, format="PNG")
        import base64
        pdf, paper, scale = make_joint_pdf(
            parcels=parcels, title="Teste de loteamento",
            owner_name="Interessado de teste", responsible_name="Técnico de teste",
            croqui=True, raster_b64=base64.b64encode(raster.getvalue()).decode("ascii"),
            raster_source="Raster teste (sintético)",
            qr_url="https://geo.amazonikaengenharia.com.br/documentos/00000000-0000-4000-8000-000000000001",
        )
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertIn(paper, {"A4", "A3", "A2", "A1", "A0"})
        self.assertGreater(scale, 0)

    def test_scale_and_paper_selection(self):
        parcels = prepare_parcels([{"name": "Lote", "geometry": self.geometry}])
        image = Image.new("RGB", (600, 350), "#487F3A")
        temp = io.BytesIO()
        image.save(temp, format="PNG")
        import base64
        source = base64.b64encode(temp.getvalue()).decode()
        output, paper, scale = make_joint_pdf(
            parcels=parcels, title="Prancha controle",
            owner_name="Cliente", responsible_name="Técnico", croqui=False,
            raster_b64=source, raster_source="Raster autorizado de teste",
            paper_format="A3", scale_denominator=1500,
        )
        self.assertTrue(output.startswith(b"%PDF-"))
        self.assertEqual(paper, "A3")
        self.assertEqual(scale, 1500)

    def test_explicit_scale_out_of_paper_is_rejected(self):
        parcels = prepare_parcels([{"name": "Lote", "geometry": self.geometry}])
        image = Image.new("RGB", (180, 120), "green")
        out = io.BytesIO()
        image.save(out, format="PNG")
        import base64
        with self.assertRaisesRegex(ValueError, "não cabe"):
            make_joint_pdf(
                parcels=parcels, title="Prancha",
                owner_name=None, responsible_name=None, croqui=False,
                raster_b64=base64.b64encode(out.getvalue()).decode(),
                raster_source="Teste", paper_format="A4", scale_denominator=100,
            )

    def test_five_vertices_single_compact_sheet_and_memorial_page(self):
        # Terreno sintético, sem atributos ou dados cadastrais reais.
        geometry = {
            "type": "Polygon",
            "coordinates": [[
                [-51.0500, 0.0500], [-51.0490, 0.0500],
                [-51.0489, 0.0507], [-51.0495, 0.0511],
                [-51.0501, 0.0508], [-51.0500, 0.0500],
            ]],
        }
        parcel = prepare_parcels([{
            "name": "Lote de validação", "geometry": geometry,
            "vertex_names": ["V01", "V02", "V03", "V04", "V05"],
        }])
        image = Image.new("RGB", (640, 360), (44, 115, 80))
        output = io.BytesIO()
        image.save(output, format="PNG")
        import base64
        generated, paper, scale = make_joint_pdf(
            parcels=parcel, title="Área sintética",
            owner_name="Pessoa fictícia", responsible_name="Técnico teste",
            croqui=False, raster_b64=base64.b64encode(output.getvalue()).decode(),
            raster_source="Imagem sintética de teste", paper_format="A3",
        )
        reader = PdfReader(io.BytesIO(generated))
        self.assertEqual(len(reader.pages), 2, "Cinco vértices devem caber na planta sem folha isolada.")
        plant = reader.pages[0].extract_text()
        self.assertIn("QUADRO DE COORDENADAS", plant)
        self.assertIn("V01", plant)
        self.assertIn("Az", plant)
        self.assertIn("D ", plant)
        memorial = reader.pages[1].extract_text()
        self.assertIn("DESCRIÇÃO DO PERÍMETRO", memorial)
        self.assertIn("Técnico teste", memorial)

    def test_memorial_matches_perimetral_model_without_inventing_values(self):
        parcels = prepare_parcels([
            {"name": "Gleba Teste", "geometry": self.geometry,
             "vertex_names": ["M01", "M02", "M03", "M04"],
             "confrontants": ["Rodovia", "Lote Vizinho", "", "Ramal"],
             "altitudes_m": [None, 12.5, None, None]},
        ])
        prose = build_joint_memorial(
            parcels, title="Fazenda Teste", owner="Pessoa Teste",
            responsible="Responsável Teste", croqui=True,
            owner_rg="RG Teste", owner_cpf="000.000.000-00",
            property_address="Área Rural Teste",
            professional={"crea": "CREA TESTE", "visto": "VISTO TESTE"},
        )
        self.assertIn("Inicia-se a descrição deste perímetro", prose)
        self.assertIn("segue confrontando com Rodovia", prose)
        self.assertIn("Latitude:", prose)
        self.assertIn("CREA TESTE", prose)
        self.assertIn("altitude: 12.50 m", prose)
        self.assertIn("Este documento se trata apenas de um croqui", prose)

    def test_memorial_word_download(self):
        parcels = prepare_parcels([
            {"name": "Lote 1", "geometry": self.geometry,
             "vertex_names": ["V01", "V02", "V03", "V04"]},
        ])
        content = build_memorial_docx(
            parcels=parcels, title="Fazenda Teste",
            memorial_heading="Memorial do lote",
            owner_name="Detentor Teste", owner_rg="RG Teste",
            owner_cpf="000.000.000-00",
            property_address="Macapá-AP",
            professional={"full_name": "Profissional Teste", "crea": "CREA TESTE"},
            include_warning=False,
        )
        self.assertTrue(content.startswith(b"PK"))
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            xml = archive.read("word/document.xml").decode()
            self.assertIn("DESCRIÇÃO DO PERÍMETRO", xml)
            self.assertIn("CREA TESTE", xml)

    def test_pdf_requires_map_raster(self):
        parcels = prepare_parcels([{"name": "Lote", "geometry": self.geometry}])
        with self.assertRaises(ValueError):
            make_joint_pdf(
                parcels=parcels, title="Lote", owner_name=None,
                responsible_name=None, croqui=False, raster_b64=None,
                raster_source=None,
            )

    def test_reject_duplicate_vertex_codes(self):
        with self.assertRaises(ValueError):
            export_polygon(
                geometry=self.geometry, filename="Lote", format="txt",
                names=["A", "A", "B", "C"],
            )


if __name__ == "__main__":
    unittest.main()
