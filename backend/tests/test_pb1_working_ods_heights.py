"""GEO124: rascunho ODS mantém dez linhas SIGEF e seis h somente em anexo."""
import io
import unittest
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from app.services.sigef_ods_working import build_working_sigef_ods
from app.services.sigef_ods import TABLE
from app.services.technical_import import parse_sigef_ods
from test_sigef_ods_reviewed import vertex,payload


class PB1WorkingOdsHeightsTests(unittest.TestCase):
    def test_ten_boundary_vertices_six_informative_heights(self):
        case=payload()
        original=case["parcels"][0]["vertices"]
        points=[]
        preliminary=[]
        for i in range(6):
            name="TEST-V-"+str(i+1).zfill(4)
            v=vertex(name,-51.39,.397-i*.001)
            v.update(sigef_method="PB1",boundary_type="LN1",
                     ellipsoidal_height_m=None,sigma_lon_m=None,sigma_lat_m=None,sigma_h_m=None)
            points.append(v)
            preliminary.append(dict(code=name,longitude=v["longitude"],latitude=v["latitude"],
                source_value_m=13.4-i*.2,h_ellipsoidal_m=-9.3-i*.2,
                local_height_rmse_loo_m=1.33,
                outside_control_hull=(i==0),status="ESTIMATIVA_NAO_VALIDADA_NAO_SUBMETER"))
        case["parcels"]=[{"name":"TESTE","number":"1","vertices":[*original[:2],*points,*original[2:]]}]
        case["preliminary_height_rows"]=preliminary
        blob=build_working_sigef_ods(case)
        with ZipFile(io.BytesIO(blob)) as archive:
            root=ET.fromstring(archive.read("content.xml"))
        names=[x.get(TABLE+"name") for x in root.iter(TABLE+"table")]
        self.assertIn("ALTURAS_PB1_PRELIMINARES",names)
        self.assertIn("AVISO_NAO_SUBMETER",names)
        self.assertIn("perimetro_1",names)
        parsed=parse_sigef_ods(blob)
        self.assertEqual(parsed["vertex_count"],10)
        records=parsed["features"][0]["properties"]["sigef_vertex_details"]
        self.assertEqual(len(records),10)
        self.assertTrue(all(v["altitude_m"] is None and v["sigma_lon_m"] is None
                            for v in records[2:8]))
        self.assertEqual(records[2]["name"],"TEST-V-0001")
        informative=next(t for t in root.iter(TABLE+"table")
                         if t.get(TABLE+"name")=="ALTURAS_PB1_PRELIMINARES")
        self.assertEqual(len(informative.findall(TABLE+"table-row")),7)
        self.assertEqual(records[0]["altitude_m"],-2.1)


if __name__=="__main__":
    unittest.main()
