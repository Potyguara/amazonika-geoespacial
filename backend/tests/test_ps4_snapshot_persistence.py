"""Regressões de persistência PS4 no snapshot do GEO90.

Não consulta banco real: confirma comportamento da rota genérica ao salvar
outra etapa do editor de peças técnicas.
"""
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from app.api.routes.technical_pieces import _validated_snapshot


class PS4SnapshotPersistenceTests(TestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=uuid4())
        self.topcon = {
            "ps4_draft": [
                {"name": "ABC-V-0001", "longitude": -51.0, "latitude": 0.1,
                 "scene_id": "SCENE-01"}
            ],
            "ps4_selected_scene": "SCENE-01",
            "ps4_ortho_report": {"scene_id": "SCENE-01", "rms_m": 1.0},
            "ps4_closure": {"confirmed": True, "signature": "v1"},
        }
        self.approved = {
            "submission": {"needs_additional_vertices": True},
            "assets": {"raster": {"sha256": "a"*64}},
            "validation": {"status": "APPROVED_BY_RT"},
            "approval": {"user_id": str(self.user.id), "approved_at": "2026-11-15T12:00:00Z"},
        }
        self.old = {
            "topcon": deepcopy(self.topcon),
            "features": {"type": "FeatureCollection", "features": []},
            "memorial_edited": "Memorial v1",
            "ps4": deepcopy(self.approved),
        }
        self.piece = SimpleNamespace(id=uuid4(), snapshot=deepcopy(self.old))

    def test_mudanca_apenas_textual_preserva_aprovacao(self):
        changed = deepcopy(self.old)
        changed.pop("ps4")
        changed["memorial_edited"] = "Memorial v2"
        result = _validated_snapshot(changed, self.piece, self.user)
        self.assertEqual(result["ps4"]["validation"]["status"], "APPROVED_BY_RT")
        self.assertEqual(result["ps4"]["approval"], self.approved["approval"])

    def test_mudanca_de_coordenada_invalida_aprovacao(self):
        changed = deepcopy(self.old)
        changed.pop("ps4")
        changed["topcon"]["ps4_draft"][0]["longitude"] = -50.99
        with patch(
            "app.api.routes.technical_pieces.evaluate_verified_ps4",
            return_value={"status": "BLOCKED", "blockers": ["Revalidar geometria."]},
        ):
            result = _validated_snapshot(changed, self.piece, self.user)
        self.assertNotIn("approval", result["ps4"])
        self.assertEqual(result["ps4"]["validation"]["status"], "BLOCKED")

    def test_proveniencia_stac_persiste_em_salvamento_comum(self):
        self.piece.snapshot["ps4"]["source_provenance"] = {
            "provider": "INPE", "item_id": "CENA-ORIGINAL",
            "technical_xml": {"status": "ARCHIVED_UNVERIFIED",
                              "sha256": "c"*64},
        }
        self.piece.snapshot["ps4"].pop("approval")
        changed = deepcopy(self.piece.snapshot)
        changed.pop("ps4")
        changed["memorial_edited"] = "Texto revisado"
        result = _validated_snapshot(changed, self.piece, self.user)
        self.assertEqual(
            result["ps4"]["source_provenance"]["item_id"],
            "CENA-ORIGINAL",
        )

    def test_rascunho_sem_laudo_preserva_cena_inpe_e_vertices_v(self):
        # Fluxo real: imagem INPE carregada, V salvos, PDF ainda ausente.
        raster_hash = "a" * 64
        self.piece.snapshot["ps4"] = {
            "assets": {"raster": {"sha256": raster_hash}},
            "import_job_id": "import-job-123",
            "source_provenance": {"provider": "INPE", "item_id": "CENA-ORIGINAL"},
            "checkpoint_analysis": {
                "raster_sha256": raster_hash,
                "checkpoints": [{"name": "M-01"}],
            },
        }
        changed = deepcopy(self.piece.snapshot)
        changed.pop("ps4")
        changed["topcon"]["ps4_draft"].append({
            "name": "ABC-V-0002", "longitude": -51.001,
            "latitude": 0.101, "scene_id": "SCENE-01",
        })
        result = _validated_snapshot(changed, self.piece, self.user)
        self.assertEqual(len(result["topcon"]["ps4_draft"]), 2)
        self.assertEqual(result["ps4"]["assets"]["raster"]["sha256"], raster_hash)
        self.assertEqual(result["ps4"]["source_provenance"]["item_id"], "CENA-ORIGINAL")
        self.assertEqual(result["ps4"]["import_job_id"], "import-job-123")
        self.assertNotIn("checkpoint_analysis", result["ps4"])
        self.assertNotIn("approval", result["ps4"])

    def test_rascunho_inalterado_preserva_checagem_compatível(self):
        raster_hash = "a" * 64
        self.piece.snapshot["ps4"] = {
            "assets": {"raster": {"sha256": raster_hash}},
            "checkpoint_analysis": {
                "raster_sha256": raster_hash, "checkpoints": [{"name": "M-01"}],
            },
        }
        changed = deepcopy(self.piece.snapshot)
        changed.pop("ps4")
        changed["memorial_edited"] = "Revisão sem alteração geométrica"
        result = _validated_snapshot(changed, self.piece, self.user)
        self.assertEqual(result["ps4"]["checkpoint_analysis"]["checkpoints"][0]["name"], "M-01")

    def test_checagem_de_outro_raster_nao_reaparece_ao_salvar(self):
        self.piece.snapshot["ps4"] = {
            "assets": {"raster": {"sha256": "a" * 64}},
            "checkpoint_analysis": {
                "raster_sha256": "b" * 64, "checkpoints": [{"name": "M-01"}],
            },
        }
        changed = deepcopy(self.piece.snapshot)
        changed.pop("ps4")
        result = _validated_snapshot(changed, self.piece, self.user)
        self.assertNotIn("checkpoint_analysis", result["ps4"])

    def test_browser_nao_consegue_injetar_aprovacao(self):
        changed = deepcopy(self.old)
        changed["ps4"] = {
            "submission": {"needs_additional_vertices": False, "vertices": []},
            "approval": {"status": "APPROVED_BY_RT", "user_id": "fraud"},
            "validation": {"status": "APPROVED_BY_RT"},
        }
        with patch(
            "app.api.routes.technical_pieces.evaluate_verified_ps4",
            return_value={"status": "NOT_APPLICABLE", "blockers": []},
        ):
            result = _validated_snapshot(changed, self.piece, self.user)
        self.assertNotIn("approval", result["ps4"])
        self.assertEqual(result["ps4"]["validation"]["status"], "NOT_APPLICABLE")
