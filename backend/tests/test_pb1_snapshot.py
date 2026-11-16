"""Testes GEO92: PB1 não reutiliza PS4 nem aceita raster falso."""
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from app.api.routes.technical_pieces import _validated_snapshot


class PB1SnapshotTests(TestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=uuid4())
        self.old = {
            "topcon": {"boundary": [{"name": "M578"}], "ps4_draft": [
                {"name": "ABC-V-0008", "longitude": -51.03, "latitude": 0.33}]},
            "pb1": {"assets": {
                "pb1_color": {"kind": "pb1_color", "sha256": "a"*64},
                "pb1_dtm": {"kind": "pb1_dtm", "sha256": "b"*64}},
                "approval": {"fake": True}},
        }
        self.piece = SimpleNamespace(id=uuid4(), snapshot=deepcopy(self.old))

    def test_pb1_nao_apaga_v_ps4(self):
        changed = deepcopy(self.old)
        changed["topcon"]["pb1_draft"] = [{
            "name": "ABC-V-0009", "longitude": -51.02, "latitude": 0.32,
            "raster_sha256": "a"*64, "source_elevation_m": 139.83
        }]
        saved = _validated_snapshot(changed, self.piece, self.user)
        self.assertEqual(len(saved["topcon"]["pb1_draft"]), 1)
        self.assertEqual(len(saved["topcon"]["ps4_draft"]), 1)
        self.assertEqual(saved["pb1"]["assets"]["pb1_color"]["sha256"], "a"*64)
        self.assertNotIn("approval", saved["pb1"])

    def test_rejeita_v_de_outro_orixp(self):
        changed = deepcopy(self.old)
        changed["topcon"]["pb1_draft"] = [{
            "name": "ABC-V-0009", "longitude": -51.02, "latitude": 0.32,
            "raster_sha256": "f"*64,
        }]
        with self.assertRaises(HTTPException) as caught:
            _validated_snapshot(changed, self.piece, self.user)
        self.assertEqual(caught.exception.status_code, 422)

    def test_nao_aceita_raster_injetado_pelo_browser(self):
        changed = deepcopy(self.old)
        changed["pb1"]["assets"]["pb1_color"]["sha256"] = "f"*64
        saved = _validated_snapshot(changed, self.piece, self.user)
        self.assertEqual(saved["pb1"]["assets"]["pb1_color"]["sha256"], "a"*64)

    def test_nao_aceita_v_sem_raster_oficial(self):
        self.piece.snapshot["pb1"] = {"assets": {}}
        changed = deepcopy(self.piece.snapshot)
        changed["topcon"]["pb1_draft"] = [{
            "name": "ABC-V-0009", "longitude": -51.02, "latitude": 0.32,
            "raster_sha256": "f"*64
        }]
        with self.assertRaises(HTTPException) as caught:
            _validated_snapshot(changed, self.piece, self.user)
        self.assertEqual(caught.exception.status_code, 422)


if __name__ == "__main__":
    import unittest
    unittest.main()
