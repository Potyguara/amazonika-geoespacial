"""Regressões do acabamento técnico da prancha, sem dados de pessoa real."""
import io
import math
import unittest
from types import SimpleNamespace

from reportlab.lib.pagesizes import A2
from reportlab.pdfgen.canvas import Canvas

from app.services.plant_detail_elements import (
    group_confrontations, grouped_label_positions, confrontations_card,
    reference_card, scale_card, signature_card, compass_rose, header_technical,
)
from app.services.plant_template_engine import Rect, PALETTES
from app.services.plant_memorial_v2 import prepare_parcels
from app.services.plant_memorial_v3 import make_joint_pdf


def parcel():
    names=["V-502","M-0305","M-0306","M-0307","M-0304"]
    segments=[
        dict(start=names[i], end=names[(i+1)%5], distance=d, azimuth=90.)
        for i,d in enumerate((908.30,401.12,2149.81,1905.33,220.27))
    ]
    return SimpleNamespace(names=names,segments=segments,
        confrontants=["Ramal São Benedito do Aporema",
                       "Dagilza Amanajás de Almeida",
                       "Fernando dos Santos Brito",
                       "Juvandira Brito da Silva",
                       "Ramal São Benedito do Aporema"])


class DetailElementsTests(unittest.TestCase):
    def test_confrontacoes_mantem_trechos_distintos_sem_perder_perimetro(self):
        p=parcel()
        groups=group_confrontations([p])
        self.assertEqual(len(groups),5)
        self.assertEqual(groups[0]["start"],"V-502")
        self.assertEqual(groups[0]["end"],"M-0305")
        self.assertEqual(groups[-1]["start"],"M-0304")
        self.assertEqual(groups[-1]["end"],"V-502")
        self.assertAlmostEqual(groups[0]["distance"],908.30,places=2)
        self.assertAlmostEqual(sum(g["distance"] for g in groups),5584.83,places=2)

    def test_rotulos_uma_vez_por_cadeia_de_confrontacao(self):
        p=parcel()
        mids=grouped_label_positions(p)
        self.assertEqual(len(mids),5)
        self.assertTrue(all(0<=index<len(p.segments) for index in mids))

    def test_cards_compactos_sao_renderizaveis(self):
        output=io.BytesIO()
        pdf=Canvas(output,pagesize=A2)
        palette=PALETTES["classic_lateral"]
        confrontations_card(pdf,Rect(25,450,350,172),[parcel()],palette)
        reference_card(pdf,Rect(25,285,350,143),22,"N",
                       convergence=.0023,palette=palette)
        scale_card(pdf,Rect(400,470,210,138),5000,palette)
        signature_card(pdf,Rect(25,44,350,227),"DETENTOR TESTE",
                       "000.000.000-00",
                       {"full_name":"ENGENHEIRO TESTE","crea":"0000",
                        "profession":"Engenheiro agrimensor","art":"ART TESTE"},
                       palette,date_text="09/11/2026")
        compass_rose(pdf,500,360,45,palette)
        header_technical(pdf,A2[0],A2[1],22,"N",5000,"09/11/2026",palette)
        pdf.save()
        self.assertTrue(output.getvalue().startswith(b"%PDF-"))
        self.assertGreater(len(output.getvalue()),4000)

    def test_modelos_profissionais_preservados_com_marcos(self):
        n=16
        x,y=-50.85,1.07
        ring=[[x+.005*math.cos(i*2*math.pi/n),
               y+.007*math.sin(i*2*math.pi/n)] for i in range(n)]
        ring.append(ring[0])
        names=[f"EQGV-M-{300+i}" if i%4==0 else f"EQGV-V-{500+i}"
               for i in range(n)]
        parcels=prepare_parcels([{
            "name":"LOTE SINTETICO",
            "geometry":{"type":"Polygon","coordinates":[ring]},
            "vertex_names":names,
            "confrontants":["VIZINHO A" if i<n//2 else "VIZINHO B"
                            for i in range(n)],
            "altitudes_m":[1.2]*n,
        }])
        flags={"situation":False,"grid":True,"vertex_labels":True,
               "north":True,"scale_text":True,"scale_bar":True,
               "coordinates":True,"azimuths":False,"distances":False,
               "confrontants":True,"technical_stamp":True}
        for model in ("classic_lateral","cartographic_frame","modern_lateral"):
            with self.subTest(model=model):
                pdf,paper,scale=make_joint_pdf(
                    parcels=parcels,title="LOTE SINTETICO",
                    owner_name="DETENTOR TESTE",owner_cpf="000.000.000-00",
                    responsible_name="ENGENHEIRO TESTE",
                    croqui=False,raster_b64=None,raster_source=None,
                    paper_format="A2",orientation="retrato",
                    layout_template=model,plant_elements=flags,
                    survey_date="2026-11-09",magnetic_declination_degrees=None,
                )
                self.assertEqual(paper,"A2")
                self.assertGreater(scale,0)
                self.assertTrue(pdf.startswith(b"%PDF-"))


if __name__=="__main__":
    unittest.main()
