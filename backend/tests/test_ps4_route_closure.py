"""Testes diretos das rotas de fechamento PS4 sem banco ou anexos reais."""
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from starlette.requests import Request

from app.api.routes.technical_pieces import (
    PS4RTAttestation, approve_ps4, get_ps4, complete_ps4_not_applicable,
)


class FakeSession:
    def __init__(self):
        self.commits = 0
    def add(self, item):
        return None
    def commit(self):
        self.commits += 1
    def refresh(self, item):
        return None


class Ps4RouteClosureTests(TestCase):
    def setUp(self):
        self.user = SimpleNamespace(
            id=uuid4(), full_name="RT EXEMPLO",
            professional_profile_json={"crea": "CREA-TESTE", "art": "ART-TESTE"},
        )
        self.db = FakeSession()
        self.request = Request({"type": "http", "method": "POST",
                                "path": "/test", "headers": []})
        self.vertex = {"name": "AAA-V-0001", "longitude": -51.01,
                       "latitude": 0.15, "scene_id": "SCENE-01"}
        self.form = {
            "needs_additional_vertices": True,
            "evidence": {
                "scene_id": "SCENE-01",
                "report_scene_id": "SCENE-01",
                "raster_sha256": "a" * 64,
                "report_sha256": "b" * 64,
                "orthorectification_rms_m": 1.0,
                "horizontal_positional_precision_m": 2.0,
                "gsd_m": 1.0, "scene_crs": "EPSG:31982",
                "feature_identifiable": True,
            },
            "vertices": [{
                "vertex_id": self.vertex["name"],
                "longitude": self.vertex["longitude"],
                "latitude": self.vertex["latitude"],
                "limit_type": "natural",
                "feature_type": "natural_feature",
            }],
        }
        self.piece = SimpleNamespace(
            id=uuid4(), status="DRAFT",
            snapshot={
                "topcon": {"ps4_draft": [deepcopy(self.vertex)]},
                "ps4": {
                    "submission": deepcopy(self.form),
                    "assets": {
                        "raster": {"kind": "raster", "sha256": "a"*64},
                        "report": {"kind": "report", "sha256": "b"*64},
                    },
                },
            },
        )
        self.all_checked = PS4RTAttestation(
            report_scene_correspondence_checked=True,
            orthorectification_rms_checked=True,
            positional_accuracy_checked=True,
            feature_identification_checked=True,
            source_resolution_checked=True,
            technical_responsibility_accepted=True,
        )

    def test_rt_approval_survives_get(self):
        with (
            patch("app.api.routes.technical_pieces._owned", return_value=self.piece),
            patch("app.api.routes.technical_pieces.evaluate_verified_ps4",
                  return_value={"status": "REVIEW_REQUIRED", "blockers": []}),
            patch("app.api.routes.technical_pieces.write_audit"),
        ):
            answer = approve_ps4(
                self.piece.id, self.all_checked, self.request, self.db, self.user,
            )
            recovered = get_ps4(self.piece.id, self.db, self.user)
        self.assertEqual(answer["ps4"]["validation"]["status"], "APPROVED_BY_RT")
        self.assertEqual(recovered["approval"]["rt_name"], "RT EXEMPLO")
        self.assertEqual(recovered["approval"]["art"], "ART-TESTE")
        self.assertEqual(self.db.commits, 1)

    def test_sem_v_conclui_e_reaparece_apos_abrir(self):
        self.piece.snapshot["ps4"]["submission"] = {
            "needs_additional_vertices": False, "vertices": [],
        }
        self.piece.snapshot["topcon"]["ps4_draft"] = []
        with (
            patch("app.api.routes.technical_pieces._owned", return_value=self.piece),
            patch("app.api.routes.technical_pieces.write_audit"),
        ):
            answer = complete_ps4_not_applicable(
                self.piece.id, self.request, self.db, self.user,
            )
            recovered = get_ps4(self.piece.id, self.db, self.user)
        self.assertEqual(answer["ps4"]["validation"]["status"], "NOT_APPLICABLE")
        self.assertIsNotNone(recovered["completed_at"])
        self.assertEqual(recovered["validation"]["status"], "NOT_APPLICABLE")
