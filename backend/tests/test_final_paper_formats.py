"""Aceite de produção: 5 tamanhos x 2 orientações x 3 modelos.

Testa imóvel pequeno (A4/A3), 61 vértices e dados técnicos completos.
"""
import io
import math
import unittest
from pypdf import PdfReader
from reportlab.lib.pagesizes import A0,A1,A2,A3,A4

from app.services.plant_memorial_v2 import prepare_parcels
from app.services.plant_memorial_v3 import make_joint_pdf
def synthetic_property(n=61):
    x,y=-50.85,1.07
    ring=[[x+.002*math.cos(2*math.pi*i/n),
           y+.003*math.sin(2*math.pi*i/n)] for i in range(n)]
    ring.append(ring[0])
    return prepare_parcels([dict(
        name="IMÓVEL DE TESTE",
        geometry={"type":"Polygon","coordinates":[ring]},
        vertex_names=[
            f"EQGV-M-{3000+i}" if i%15==0 else f"EQGV-V-{500+i}"
            for i in range(n)
        ],
        altitudes_m=[1.1]*n,
        confrontants=["Ramal São Benedito do Aporema" if i<15 else
                      "Confrontante Sul" if i<32 else
                      "Confrontante Oeste" for i in range(n)],
    )])

SIZES={"A0":A0,"A1":A1,"A2":A2,"A3":A3,"A4":A4}
LAYOUTS=("classic_lateral","cartographic_frame","modern_lateral")
FLAGS=dict(grid=True,north=True,scale_text=True,scale_bar=True,
           vertex_labels=True,azimuths=False,distances=False,
           confrontants=True,coordinates=True,situation=False,
           magnetic_declination=False,technical_stamp=True)


def small_property():
    x,y=-50.85,1.07
    ring=[[x,y],[x+.0002,y],[x+.0002,y+.00017],[x,y+.00017],[x,y]]
    return prepare_parcels([dict(
        name="LOTE PEQUENO",
        geometry={"type":"Polygon","coordinates":[ring]},
        vertex_names=["EQGV-M-001","EQGV-V-002","EQGV-V-003","EQGV-V-004"],
        altitudes_m=[3.1]*4,
        confrontants=["Via pública","Imóvel A","Imóvel B","Imóvel C"],
    )])


def build(fmt,orientation,layout,large=False):
    data,format_returned,scale=make_joint_pdf(
        parcels=synthetic_property() if large else small_property(),
        title="IMÓVEL DE TESTE", owner_name="DETENTOR DE TESTE",
        owner_rg="123456",owner_cpf="000.000.000-00",
        responsible_name="RESPONSÁVEL DE TESTE",
        professional={
            "full_name":"RESPONSÁVEL DE TESTE",
            "profession":"Engenheiro Florestal",
            "specialization":"Georreferenciamento de imóveis rurais",
            "crea":"CREA 1234567890",
            "visto":"Visto AP 123",
            "art":"ART DAP000000",
        },
        croqui=False,raster_b64=None,raster_source=None,
        paper_format=fmt,orientation=orientation,
        layout_template=layout,plant_elements=FLAGS,
        survey_date="2026-11-09",
    )
    assert format_returned==fmt and scale>0
    return PdfReader(io.BytesIO(data))


class AllFormatsAcceptanceTest(unittest.TestCase):
    def test_small_properties_all_30_combinations(self):
        for paper in SIZES:
            for orientation in ("retrato","paisagem"):
                for layout in LAYOUTS:
                    with self.subTest(paper=paper,orientation=orientation,
                                      layout=layout):
                        reader=build(paper,orientation,layout)
                        self.assertGreaterEqual(len(reader.pages),2)
                        first=reader.pages[0].mediabox
                        w,h=float(first.width),float(first.height)
                        self.assertEqual(w>h,orientation=="paisagem")
                        self.assertAlmostEqual(
                            sorted((w,h))[0],sorted(SIZES[paper])[0],delta=2
                        )
                        text="\n".join(p.extract_text() for p in reader.pages)
                        self.assertIn("RESPONSÁVEL DE TESTE",text)
                        self.assertIn("CONFRONTAÇÕES",text)
                        self.assertIn("DESCRIÇÃO DO PERÍMETRO",text)
                        self.assertIn("EQGV-M-001",text)

    def test_61_vertices_all_models_on_a3_a4(self):
        for paper in ("A3","A4"):
            for orientation in ("retrato","paisagem"):
                for layout in LAYOUTS:
                    with self.subTest(paper=paper,orientation=orientation,
                                      layout=layout):
                        reader=build(paper,orientation,layout,large=True)
                        text="\n".join(p.extract_text() for p in reader.pages)
                        self.assertIn("EQGV-M-3000",text)
                        self.assertIn("EQGV-V-550",text)
                        self.assertIn("QUADRO DE COORDENADAS",text)
                        self.assertIn("Ramal São Benedito do Aporema",text)


if __name__=="__main__":
    unittest.main()
