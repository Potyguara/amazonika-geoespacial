"""Integração de rotas PS1 com arquivos/DB simulados, usando ODS real."""
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from uuid import uuid4

from fastapi import HTTPException
from app.api.routes import technical_pieces as routes
from app.services.technical_import import parse_sigef_ods
from test_sigef_ods_reviewed import payload


class PS1RouteTests(unittest.TestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=uuid4(), professional_profile_json={"crea":"TESTE","art":"TESTE"})
        self.case = payload()
        self.boundary = deepcopy(self.case["parcels"][0]["vertices"])
        for v in self.boundary:
            v.update(parcel_number="1", parcel_name="LOTE A")
        extent = {"type":"Polygon","coordinates":[[[-52,0],[-50,0],[-50,1],[-52,1],[-52,0]]]}
        assets = {k:{"kind":k,"sha256":"a"*64,"metadata":{"wgs84_extent":extent,"bands":[{}]}}
                  for k in ("ps1_ortho","ps1_dtm","ps1_report")}
        self.piece = SimpleNamespace(id=uuid4(),snapshot={"topcon":{"boundary":self.boundary},"ps1":{"assets":assets}})
        self.db = MagicMock()
        self.db.scalar.return_value = self.piece
        self.request = SimpleNamespace(client=None,headers={})
        self.input = routes.PS1FinalizeInput(
            start="TEST-M-0001", vertices=[{"code":"TEST-V-0001","longitude":-51.395,"latitude":.395}],
            checkpoints=[{"id":"C1","used_for_control":False,"delta_e_m":.1,"delta_n_m":.2,"delta_h_m":.3}],
            category="ARTIFICIAL",vertical_kind="ELLIPSOIDAL",vertical_reference="SIRGAS2000",
            report_reference="RELATORIO TESTE",gsd_m=.05,pec_reference="PEC TESTE",
            rt_reviewed=True,gsd_compatible=True,pec_compatible=True,
            independent_sample_representative=True,report_matches_assets_and_residuals=True,
            datum_and_vertical_accuracy_checked=True,sirgas2000_and_boundaries_checked=True)

    def test_finalize_save_export_and_reject_mutation(self):
        with patch.object(routes,"exists_matching",return_value=True), patch.object(routes,"write_audit"), patch("app.services.pb1_dtm_sampling.sample_pb1_dtm",return_value=12.):
            result=routes.finalize_ps1(self.piece.id,self.input,self.request,self.db,self.user)
            self.assertEqual(self.piece.snapshot["ps1"]["approval"]["status"],"APPROVED_BY_RT")
            self.db.commit.assert_called()
            # Simula o payload de adoção da geometria produzido pela interface.
            incoming={"topcon":{"boundary":deepcopy(result["vertices"])}}
            self.piece.snapshot=routes._validated_snapshot(incoming,self.piece,self.user)
            self.assertEqual(self.piece.snapshot["ps1"]["approval"]["status"],"APPROVED_BY_RT")
            case=deepcopy(self.case)
            case["parcels"][0]["vertices"]=result["vertices"]
            case["piece_id"]=self.piece.id
            response=routes.export_reviewed_sigef_ods(routes.ReviewedSigefOdsInput(**case),self.db,self.user)
            parsed=parse_sigef_ods(response.body)
            self.assertIn("TEST-V-0001",parsed["features"][0]["properties"]["vertexNames"])
            case["parcels"][0]["vertices"]=deepcopy(result["vertices"])
            case["parcels"][0]["vertices"][1]["sigma_lon_m"]=.01
            with self.assertRaises(HTTPException) as ctx:
                routes.export_reviewed_sigef_ods(routes.ReviewedSigefOdsInput(**case),self.db,self.user)
            self.assertEqual(ctx.exception.status_code,422)

    def test_missing_evidence(self):
        with patch.object(routes,"exists_matching",return_value=False):
            with self.assertRaises(HTTPException) as ctx:
                routes.finalize_ps1(self.piece.id,self.input,self.request,self.db,self.user)
        self.assertEqual(ctx.exception.status_code,422)
        self.db.commit.assert_not_called()
