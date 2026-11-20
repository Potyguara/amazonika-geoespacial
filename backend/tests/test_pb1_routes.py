"""Integração das rotas PB1 com banco e amostragem simulados, ODS real."""
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException
from app.api.routes import technical_pieces as routes
from app.services.technical_import import parse_sigef_ods
from test_sigef_ods_reviewed import payload, vertex


class PB1RouteTests(TestCase):
    def setUp(self):
        self.case = payload()
        self.m = deepcopy(self.case["parcels"][0]["vertices"])
        self.v = vertex("TEST-V-0001", -51.395, .395)
        self.v.update(sigef_method="PB1", boundary_type="LN1",
                      ellipsoidal_height_m=12., sigma_lon_m=.6, sigma_lat_m=.8,
                      sigma_h_m=.2)
        self.case["parcels"][0]["vertices"] = [self.m[0], self.v, *self.m[1:]]
        self.draft = [dict(name=self.v["name"], longitude=self.v["longitude"],
                           latitude=self.v["latitude"], raster_sha256="b"*64)]
        self.source = dict(product="Produto cartográfico oficial de teste",
                           accuracy_reference="Ficha técnica de teste",
                           vertical_reference="Ficha vertical de teste",
                           vertical_kind="ELLIPSOIDAL", vertical_datum="SIRGAS 2000",
                           source_model="NONE")
        self.user = SimpleNamespace(id=uuid4(), professional_profile_json=dict(crea="TESTE", art="TESTE", incra_code="TEST"))
        self.piece = SimpleNamespace(id=uuid4(), snapshot={
            "topcon": {"boundary":self.m, "pb1_draft":self.draft,
                       "pb1_source":self.source, "pb1_closure":{"start":self.m[0]["name"], "confirmed":False}},
            "pb1":{"assets":{"pb1_dtm":{"kind":"pb1_dtm", "sha256":"b"*64, "metadata":{"bands":[{}]}}}}})
        self.case["piece_id"] = self.piece.id
        self.db = MagicMock()
        self.db.scalar.return_value = self.piece
        self.request = SimpleNamespace(client=None, headers={})

    def calculate(self):
        return routes.pb1_process_partial(self.piece.id, routes.PB1PartialInput(
            sigma_e_m=.6, sigma_n_m=.8, source_sigma_m=.2), self.db, self.user)

    def approve(self):
        return routes.approve_pb1(self.piece.id, routes.PB1ApproveInput(
            vertices=self.case["parcels"][0]["vertices"], category="NATURAL",
            position_reference="Base oficial de teste, ficha técnica e folha conferidas",
            rt_reviewed=True), self.request, self.db, self.user)

    def export(self):
        return routes.export_reviewed_sigef_ods(routes.ReviewedSigefOdsInput(**self.case),
                                                self.db, self.user)

    def close(self):
        incoming=deepcopy(self.piece.snapshot)
        incoming["topcon"]["pb1_closure"]["confirmed"]=True
        incoming["features"]={"type":"FeatureCollection","features":[]}
        self.piece.snapshot=routes._validated_snapshot(incoming,self.piece,self.user)

    @patch.object(routes,"exists_matching",return_value=True)
    @patch.object(routes,"write_audit")
    @patch("app.services.pb1_dtm_sampling.sample_pb1_dtm",return_value=12.)
    def test_mdt_only_calculate_close_approve_export_and_reject_change(self,*mocks):
        self.calculate()
        self.close()
        self.assertIn("partial_preview",self.piece.snapshot["pb1"])
        with self.assertRaises(HTTPException):
            self.export()
        self.approve()
        response=self.export()
        parsed=parse_sigef_ods(response.body)
        self.assertIn("TEST-V-0001",parsed["features"][0]["properties"]["vertexNames"])
        self.case["parcels"][0]["vertices"][1]["sigma_lon_m"]=.5
        with self.assertRaises(HTTPException):
            self.export()
        incoming=deepcopy(self.piece.snapshot)
        incoming["topcon"]["pb1_source"]["accuracy_reference"]="Outro documento"
        self.piece.snapshot=routes._validated_snapshot(incoming,self.piece,self.user)
        self.assertNotIn("approval",self.piece.snapshot["pb1"])

    @patch.object(routes,"exists_matching",return_value=True)
    def test_working_ods_adds_server_issued_local_height_only_to_informative_sheet(self,*mocks):
        from io import BytesIO
        from zipfile import ZipFile
        self.case["parcels"][0]["vertices"][1]["ellipsoidal_height_m"]=None
        self.piece.snapshot["pb1"]["partial_preview"]={
            "dtm_sha256":"b"*64,
            "points":[{
                "vertex_id":self.v["name"],"latitude":self.v["latitude"],
                "longitude":self.v["longitude"],"source_value_m":12.7,
                "h_ellipsoidal_m":-10.04,"local_height_rmse_loo_m":1.33,
                "outside_control_hull":False,
                "status":"LOCAL_ESTIMATE_UNVALIDATED",
            }],
        }
        result=routes.download_working_sigef_ods(
            routes.ReviewedSigefOdsInput(**self.case),self.db,self.user)
        with ZipFile(BytesIO(result.body)) as archive:
            xml=archive.read("content.xml").decode()
            self.assertIn("ALTURAS_PB1_PRELIMINARES",xml)
            self.assertIn("ESTIMATIVA_NAO_VALIDADA_NAO_SUBMETER",xml)
            self.assertIn("TEST-V-0001",xml)
        parsed=parse_sigef_ods(result.body)
        self.assertIsNone(parsed["features"][0]["properties"]["sigef_vertex_details"][1]["altitude_m"])

    @patch.object(routes,"exists_matching",return_value=True)
    @patch("app.services.pb1_dtm_sampling.sample_pb1_dtm",side_effect=ValueError("NoData"))
    def test_rejects_nodata(self,*mocks):
        with self.assertRaises(HTTPException) as ctx:
            self.calculate()
        self.assertEqual(ctx.exception.status_code,422)
