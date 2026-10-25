from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

from app.services.geospatial_export import export_polygon
from app.services.plant_memorial_v2 import prepare_parcels, make_joint_pdf


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
        )
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertIn(paper, {"A4", "A3", "A2", "A1", "A0"})
        self.assertGreater(scale, 0)

    def test_reject_duplicate_vertex_codes(self):
        with self.assertRaises(ValueError):
            export_polygon(
                geometry=self.geometry, filename="Lote", format="txt",
                names=["A", "A", "B", "C"],
            )


if __name__ == "__main__":
    unittest.main()
