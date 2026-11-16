"""Fluxo de importação STAC no endpoint privado da peça técnica."""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from app.api.routes.technical_pieces import (
    PS4InpeCropInput, ps4_prepare_inpe_scene,
)


class DummyDB:
    def add(self, _): pass
    def commit(self): pass
    def refresh(self, _): pass


class PS4InpeRoutesTests(TestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=uuid4())
        self.piece = SimpleNamespace(id=uuid4(), status="DRAFT", snapshot={
            "ps4": {
                "assets": {
                    "raster": {"sha256": "b"*64, "kind": "raster"},
                    "report": {"sha256": "c"*64, "kind": "report"},
                },
                "approval": {"status": "APPROVED_BY_RT"},
                "completed_at": "2026-11-15T12:00:00Z",
                "source_provenance": {"item_id": "OLD"},
            },
        })
        self.payload = PS4InpeCropInput(
            item_id="CBERS4A_WPM_PCA_RGB321_20260410_196_132",
            collection="CB4A-WPM-PCA-FUSED-1",
            bbox=(-51.0005, 0.0, -51.0002, 0.0003),
        )
        self.stac = {
            "id": self.payload.item_id,
            "collection": self.payload.collection,
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-52, -1], [-50, -1], [-50, 1], [-52, 1], [-52, -1],
                ]],
            },
        }

    def test_novo_recorte_revoga_documentos_e_aprovacao_antigos(self):
        with (
            patch("app.api.routes.technical_pieces._owned", return_value=self.piece),
            patch("app.api.routes.technical_pieces.fetch_inpe_item",
                  return_value=self.stac),
            patch("app.api.routes.technical_pieces.import_inpe_crop",
                  return_value={
                      "asset": {"sha256": "a"*64, "kind": "raster"},
                      "provenance": {"provider": "INPE", "item_id": self.payload.item_id},
                  }),
        ):
            answer = ps4_prepare_inpe_scene(
                self.piece.id, self.payload, DummyDB(), self.user,
            )
        self.assertEqual(answer["ps4"]["assets"]["raster"]["sha256"], "a"*64)
        self.assertNotIn("report", answer["ps4"]["assets"])
        self.assertNotIn("approval", answer["ps4"])
        self.assertNotIn("completed_at", answer["ps4"])
        self.assertEqual(answer["source_provenance"]["item_id"], self.payload.item_id)

    def test_fora_da_geometria_stac_rejeitado_sem_importar(self):
        outside = self.payload.model_copy(
            update={"bbox": (-47.0, 0.0, -46.9999, 0.0003)}
        )
        with (
            patch("app.api.routes.technical_pieces._owned", return_value=self.piece),
            patch("app.api.routes.technical_pieces.fetch_inpe_item",
                  return_value=self.stac),
            patch("app.api.routes.technical_pieces.import_inpe_crop") as importer,
        ):
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as error:
                ps4_prepare_inpe_scene(
                    self.piece.id, outside, DummyDB(), self.user,
                )
        self.assertEqual(error.exception.status_code, 422)
        importer.assert_not_called()
