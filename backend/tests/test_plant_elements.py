"""Regressão sem rede: prancha PDF com opções de elementos e imagem 4:3."""
from __future__ import annotations

import base64
import io
import unittest

from PIL import Image
from app.services.plant_memorial_v2 import prepare_parcels
from app.services.plant_memorial_v3 import make_joint_pdf


class PlantElementsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        geometry = {
            "type": "Polygon",
            "coordinates": [[
                [-51.05, -0.05],
                [-51.0497, -0.05],
                [-51.0497, -0.0497],
                [-51.05, -0.0497],
                [-51.05, -0.05],
            ]],
        }
        cls.parcels = prepare_parcels([{
            "name": "Área de teste",
            "geometry": geometry,
            "vertex_names": ["V01", "V02", "V03", "V04"],
            "confrontants": ["A", "B", "C", "D"],
        }])
        img = Image.new("RGB", (640, 480), (224, 233, 228))
        stream = io.BytesIO()
        img.save(stream, format="JPEG")
        cls.image = base64.b64encode(stream.getvalue()).decode("ascii")

    def build(self, **kwargs):
        return make_joint_pdf(
            parcels=self.parcels,
            title="Imóvel Teste",
            owner_name="Detentor Teste",
            owner_rg=None,
            owner_cpf=None,
            property_address="Macapá, AP",
            responsible_name="Responsável Teste",
            professional={"full_name": "Responsável Teste", "crea": "AP-12345"},
            croqui=False,
            raster_b64=self.image,
            raster_source="Imagem de teste",
            paper_format="A4",
            orientation="paisagem",
            **kwargs,
        )

    def test_padrao_gera_pdf(self):
        pdf, sheet, scale = self.build()
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertEqual(sheet, "A4")
        self.assertGreaterEqual(scale, 50)

    def test_elementos_podem_ser_ocultados(self):
        pdf, _, _ = self.build(plant_elements={
            "coordinates": False,
            "grid": False,
            "north": False,
            "vertex_labels": False,
            "situation": False,
            "technical_stamp": False,
            "scale_text": False,
        })
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_declination_wmm2025_calculada_sem_valor_manual(self):
        pdf, _, _ = self.build(
            plant_elements={"magnetic_declination": True},
            survey_date="2026-10-27",
        )
        self.assertTrue(pdf.startswith(b"%PDF"))
        from pypdf import PdfReader
        text=" ".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
        self.assertIn("WMM2025",text)

    def test_declination_manual_preservada(self):
        pdf, _, _ = self.build(
            plant_elements={"magnetic_declination": True},
            magnetic_declination_degrees=-15.5,
        )
        self.assertTrue(pdf.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
