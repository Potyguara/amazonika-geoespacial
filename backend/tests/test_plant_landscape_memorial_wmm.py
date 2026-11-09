"""Critérios de aceite: paisagem A2/A1, WMM, quadros e memoriais A/B/C."""
import io
import math
import unittest
from datetime import date
from types import SimpleNamespace

from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.pagesizes import A2

from app.services.plant_memorial_v2 import prepare_parcels
from app.services.plant_memorial_v3 import make_joint_pdf
from app.services.plant_geomagnetism import resolve_magnetic_declination
from app.services.plant_detail_elements import confrontations_card
from app.services.plant_template_engine import Rect, PALETTES


def synthetic_property(n=61):
    center=(-50.87, 1.085)
    ring=[
        [center[0]+.005*math.cos(i*2*math.pi/n),
         center[1]+.008*math.sin(i*2*math.pi/n)]
        for i in range(n)
    ]
    ring.append(ring[0])
    names=[
        f"EQGV-M-{3000+i}" if i%15==0 else f"EQGV-V-{500+i}"
        for i in range(n)
    ]
    bordering=[
        "Ramal São Benedito do Aporema" if i<9 or i>n-5 else
        "Confrontante longo de teste com muitas palavras" if i<20 else
        "Confrontante B" if i<50 else "Confrontante C"
        for i in range(n)
    ]
    return prepare_parcels([{
        "name":"ÁREA SINTÉTICA",
        "geometry":{"type":"Polygon","coordinates":[ring]},
        "vertex_names":names,
        "altitudes_m":[1.5]*n,
        "confrontants":bordering,
    }])


FLAGS=dict(
    grid=True,north=True,scale_text=True,scale_bar=True,
    vertex_labels=True,azimuths=True,distances=True,
    confrontants=True,coordinates=True,situation=False,
    magnetic_declination=True,technical_stamp=True,
)


def export(template,orientation="retrato",magnetic=True):
    data,paper,scale=make_joint_pdf(
        parcels=synthetic_property(),title="ÁREA SINTÉTICA",
        owner_name="DETENTOR DE TESTE",owner_rg="1234",
        owner_cpf="000.000.000-00",responsible_name="TÉCNICO DE TESTE",
        professional={
            "full_name":"TÉCNICO DE TESTE",
            "profession":"Engenheiro agrimensor",
            "specialization":"Georreferenciamento rural",
            "crea":"CREA TESTE",
            "visto":"VISTO TESTE",
            "incra_code":"CRED. TESTE",
            "art":"ART TESTE",
        },
        property_address="Município de teste, AP",
        croqui=False,raster_b64=None,raster_source=None,
        paper_format="A2",orientation=orientation,
        layout_template=template,
        plant_elements={**FLAGS,"magnetic_declination":magnetic},
        survey_date="2026-11-09",magnetic_declination_degrees=None,
        property_metadata={"legal_status":"Área particular",
                           "area_nature":"Particular"},
    )
    return PdfReader(io.BytesIO(data)),paper,scale


class FinalPlantAndMemorialTests(unittest.TestCase):
    def test_wmm2025_returns_value_for_northernmost_vertex(self):
        d,source=resolve_magnetic_declination(
            synthetic_property(),date(2026,11,9),enabled=True
        )
        self.assertTrue(math.isfinite(d))
        self.assertLess(abs(d),90)
        self.assertIn("WMM2025",source)

    def test_manual_magnetic_override(self):
        d,source=resolve_magnetic_declination(
            synthetic_property(),date(2026,11,9),enabled=True,
            manual_degrees=-12.3
        )
        self.assertAlmostEqual(d,-12.3)
        self.assertIn("responsável técnico",source)

    def test_three_templates_preserve_paper_and_memorial(self):
        for template in ("classic_lateral","cartographic_frame","modern_lateral"):
            with self.subTest(template=template):
                reader,paper,scale=export(template)
                self.assertGreaterEqual(len(reader.pages),2)
                self.assertGreater(scale,0)
                self.assertEqual(paper,"A2")
                page0=reader.pages[0]
                self.assertLess(float(page0.mediabox.width),float(page0.mediabox.height))
                self.assertIn("DECLINAÇÃO",page0.extract_text().upper())
                all_text="\n".join(p.extract_text() for p in reader.pages[1:])
                self.assertIn("CONFRONTAÇÕES",all_text)
                self.assertIn("CROQUI ESQUEMÁTICO",all_text)
                self.assertIn("DESCRIÇÃO DO PERÍMETRO",all_text)
                self.assertIn("TÉCNICO DE TESTE",all_text)

    def test_landscape_real_orientation_and_coordinate_continuation(self):
        for template in ("classic_lateral","cartographic_frame","modern_lateral"):
            with self.subTest(template=template):
                reader,paper,scale=export(template,"paisagem")
                self.assertGreaterEqual(len(reader.pages),3)
                self.assertGreater(float(reader.pages[0].mediabox.width),
                                   float(reader.pages[0].mediabox.height))
                # A folha complementar mantém a relação de aspecto horizontal.
                self.assertGreater(float(reader.pages[1].mediabox.width),
                                   float(reader.pages[1].mediabox.height))
                self.assertIn("QUADRO DE COORDENADAS",reader.pages[1].extract_text())

    def test_long_confrontation_names_do_not_stop_pdf_generation(self):
        stream=io.BytesIO()
        pdf=Canvas(stream,pagesize=A2)
        confrontations_card(pdf,Rect(33,100,310,240),
                            synthetic_property(),PALETTES["classic_lateral"])
        pdf.save()
        self.assertIn("PERÍMETRO TOTAL",PdfReader(stream).pages[0].extract_text())


if __name__=="__main__":
    unittest.main()
