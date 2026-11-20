"""GEO123: aferição M–V e roundtrip ODS em perímetro sintético de dez pontos.
Os dados não são as medições da Fazenda Shikama nem aprovação SIGEF.
"""
import unittest
from copy import deepcopy
from app.services.pb1_ods_audit import audit_pb1_ods
from app.services.sigef_ods_reviewed import build_reviewed_sigef_ods
from app.services.technical_import import parse_sigef_ods
from test_sigef_ods_reviewed import payload, vertex

class PB1TenVertices(unittest.TestCase):
    def setUp(self):
        original=[
            vertex("TEST-M-0001",-51.4,.4),
            vertex("TEST-M-0002",-51.39,.4),
            vertex("TEST-M-0003",-51.39,.39),
            vertex("TEST-M-0004",-51.4,.39),
        ]
        for p in original:
            p["name"]=p["sigef_vertex_code"]
        vs=[]
        for i in range(6):
            code=f"TEST-V-{i+1:04d}"
            p=vertex(code,-51.39,.3986-i*.0014)
            p.update(name=code,sigef_method="PB1",boundary_type="LN1",
                     ellipsoidal_height_m=-10.25-i/5,
                     sigma_lon_m=.25,sigma_lat_m=.3,sigma_h_m=.5,
                     derived_calculation={"method":"PB1","accuracy_verified":True})
            vs.append(p)
        self.vertices=[*original[:2],*vs,*original[2:]]
        self.snapshot={
            "topcon":{"boundary":original,
                      "pb1_closure":{"confirmed":True,"start":original[1]["name"]},
                      "pb1_draft":[dict(name=v["name"],longitude=v["longitude"],latitude=v["latitude"]) for v in vs],
                      "pb1_source":{"product":"Produto de ensaio com referência",
                                    "accuracy_reference":"Relatório de controle hipotético",
                                    "vertical_reference":"Ficha de referência hipotética"}},
            "pb1":{"assets":{"pb1_dtm":{"sha256":"a"*64}},
                   "partial_preview":{"sigma_origin":"DECLARED","points":[
                       dict(vertex_id=v["name"],longitude=v["longitude"],latitude=v["latitude"],
                            status="DECLARED_REFERENCE",h_ellipsoidal_m=v["ellipsoidal_height_m"],
                            sigma_e_m=v["sigma_lon_m"],sigma_n_m=v["sigma_lat_m"],sigma_h_m=v["sigma_h_m"])
                       for v in vs]}}
        }
        self.case=payload()
        self.case["parcels"]=[{"number":"1","name":"TESTE DE DEZ VÉRTICES","vertices":self.vertices}]

    def test_diagnostics_complete_but_do_not_certify(self):
        result=audit_pb1_ods(self.snapshot,self.vertices)
        self.assertEqual(result["status"],"READY_FOR_RT_REVIEW")
        self.assertEqual(result["vertex_count"],10)
        self.assertEqual(result["original_count"],4)
        self.assertEqual(result["pb1_count"],6)
        self.assertEqual(result["complete_count"],10)
        self.assertIn("não substitui",result["notice"])

    def test_local_estimate_blocks_six_pb1_rows(self):
        for row in self.snapshot["pb1"]["partial_preview"]["points"]:
            row["status"]="LOCAL_ESTIMATE_UNVALIDATED"
            row["sigma_h_m"]=None
            row["sigma_e_m"]=None
            row["sigma_n_m"]=None
        self.snapshot["pb1"]["partial_preview"]["sigma_origin"]="MISSING"
        for v in self.vertices[2:8]:
            v.update(height_reference_confirmed=False,sigma_lon_m=None,
                     sigma_lat_m=None,sigma_h_m=None)
        result=audit_pb1_ods(self.snapshot,self.vertices)
        self.assertEqual(result["status"],"PENDING")
        self.assertEqual(result["complete_count"],4)
        self.assertEqual(sum(not r["ready"] for r in result["vertices"]),6)
        self.assertTrue(all("LOCAL_ESTIMATE_UNVALIDATED" in
                            " ".join(r["reasons"]) for r in result["vertices"][2:8]))

    def test_edited_pb1_attributes_detected(self):
        self.vertices[2]["sigma_lon_m"]=.03
        check=audit_pb1_ods(self.snapshot,self.vertices)
        self.assertEqual(check["complete_count"],9)
        self.assertIn("divergente",str(check["vertices"][2]["reasons"]))

    def test_ods_template_roundtrip_all_ten_negative_heights_and_sigmas(self):
        # ODS apenas quando os seis PB1 provêm de aprovação autenticada
        with self.assertRaisesRegex(ValueError,"PB1 sem aprovação"):
            build_reviewed_sigef_ods(self.case)
        approved=deepcopy(self.vertices[2:8])
        blob=build_reviewed_sigef_ods(self.case,approved_pb1_vertices=approved)
        result=parse_sigef_ods(blob)
        self.assertEqual(result["vertex_count"],10)
        points=result["features"][0]["properties"]["sigef_vertex_details"]
        self.assertEqual([p["name"] for p in points],[p["sigef_vertex_code"] for p in self.vertices])
        for original,readback in zip(self.vertices,points):
            self.assertAlmostEqual(readback["altitude_m"],original["ellipsoidal_height_m"],places=3)
            self.assertAlmostEqual(readback["sigma_lon_m"],original["sigma_lon_m"],places=3)
            self.assertAlmostEqual(readback["sigma_lat_m"],original["sigma_lat_m"],places=3)
            self.assertAlmostEqual(readback["sigma_altitude_m"],original["sigma_h_m"],places=3)
            self.assertEqual(readback["positioning_method"],original["sigef_method"])
            self.assertEqual(readback["boundary_type"],original["boundary_type"])
            self.assertEqual(readback["confrontant"],original["confrontant"])
