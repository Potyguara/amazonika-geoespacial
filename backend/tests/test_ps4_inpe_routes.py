"""Rotas assíncronas de importação INPE e isolamento por usuário."""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4, UUID

from fastapi import HTTPException

from app.api.routes.technical_pieces import (
    PS4InpeCropInput, ps4_prepare_inpe_scene, ps4_inpe_job_status,
)


class DummyDB:
    def add(self, _): pass
    def commit(self): pass
    def refresh(self, _): pass


class PS4InpeRoutesTests(TestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=uuid4())
        self.piece = SimpleNamespace(id=uuid4(), status="DRAFT", snapshot={"ps4": {}})
        self.payload = PS4InpeCropInput(
            item_id="CBERS4A_WPM_PCA_RGB321_20260410_196_132",
            collection="CB4A-WPM-PCA-FUSED-1",
            bbox=(-51.0005, 0.0, -51.0002, 0.0003),
        )
        self.db = DummyDB()

    def test_enfileira_sem_chamar_inpe_gdal_no_http(self):
        with (
            patch("app.api.routes.technical_pieces._owned", return_value=self.piece),
            patch("app.api.routes.technical_pieces.save_job") as queue,
        ):
            response = ps4_prepare_inpe_scene(
                self.piece.id, self.payload, self.db, self.user,
            )
        self.assertEqual(response["job"]["status"], "QUEUED")
        self.assertEqual(self.piece.snapshot["ps4"]["import_job_id"],
                         response["job"]["id"])
        queue.assert_called_once()
        job = queue.call_args.args[0]
        self.assertNotIn("source_href", job)

    def test_nao_duplica_job_ativo(self):
        old = str(uuid4())
        self.piece.snapshot["ps4"]["import_job_id"] = old
        with (
            patch("app.api.routes.technical_pieces._owned", return_value=self.piece),
            patch("app.api.routes.technical_pieces.read_job",
                  return_value={"id": old, "status": "PROCESSING"}),
        ):
            with self.assertRaises(HTTPException) as error:
                ps4_prepare_inpe_scene(
                    self.piece.id, self.payload, self.db, self.user,
                )
        self.assertEqual(error.exception.status_code, 409)

    def test_job_nao_vinculado_nao_e_visivel(self):
        self.piece.snapshot["ps4"]["import_job_id"] = str(uuid4())
        with patch("app.api.routes.technical_pieces._owned", return_value=self.piece):
            with self.assertRaises(HTTPException) as error:
                ps4_inpe_job_status(self.piece.id, uuid4(), self.db, self.user)
        self.assertEqual(error.exception.status_code, 404)

    def test_job_vinculado_ao_usuario(self):
        job_id = uuid4()
        self.piece.snapshot["ps4"]["import_job_id"] = str(job_id)
        with (
            patch("app.api.routes.technical_pieces._owned", return_value=self.piece),
            patch("app.api.routes.technical_pieces.read_job",
                  return_value={
                      "id": str(job_id),
                      "piece_id": str(self.piece.id),
                      "user_id": str(uuid4()),
                      "status": "READY",
                  }),
        ):
            with self.assertRaises(HTTPException) as error:
                ps4_inpe_job_status(self.piece.id, job_id, self.db, self.user)
        self.assertEqual(error.exception.status_code, 404)
