"""GEO99: ODS de trabalho deve conservar dados e lacunas sem fabricar precisão."""
import unittest
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from app.services.sigef_ods_working import build_working_sigef_ods
from app.services.sigef_ods import TABLE, TEXT

class Geo99WorkingOdsTest(unittest.TestCase):
    def test_draft_contains_real_vertices_blank_unknown_and_notice(self):
        vertices=[]
        for i, (lon,lat) in enumerate([
            (-50.9,.42),(-50.89,.40),(-50.91,.39),
        ]):
            vertices.append({
                "sigef_vertex_code":("CPBR-M-0001" if i==0 else f"CPBR-V-{i:04d}"),
                "longitude":lon,"latitude":lat,
                "ellipsoidal_height_m":(-17.695 if i==0 else None),
                "sigma_lon_m":None,"sigma_lat_m":None,"sigma_h_m":None,
                "sigef_method":"PS4" if i else "PG1",
                "boundary_type":"LN1","confrontant":"Benedito",
            })
        raw=build_working_sigef_ods({
            "identification":{"holder_name":"Teste","property_name":"Teste de campo"},
            "parcels":[{"name":"Teste","number":"1","vertices":vertices}],
        })
        with ZipFile(BytesIO(raw)) as package:
            xml=package.read("content.xml")
            assert package.testzip() is None
            root=ET.fromstring(xml)
            self.assertIn(b"CPBR-V-0002",xml)
            self.assertIn(b"AVISO_NAO_SUBMETER",xml)
            self.assertIn(b"RASCUNHO INCOMPLETO",xml)
            perim=next(s for s in root.findall(f".//{TABLE}table") if s.attrib.get(TABLE+"name")=="perimetro_1")
            rows=perim.findall(TABLE+"table-row")
            for offset in (12,13,14):
                line=rows[offset-1]
                cells=[x for x in line if x.tag in (TABLE+"table-cell",TABLE+"covered-table-cell")]
                self.assertEqual(len(cells)>=12,True)
                self.assertEqual(cells[2].findtext(TEXT+"p"),"")
                self.assertEqual(cells[4].findtext(TEXT+"p"),"")
                self.assertEqual(cells[6].findtext(TEXT+"p"),"")
            self.assertEqual(cells[5].findtext(TEXT+"p"),"")

if __name__=="__main__":
    unittest.main()
