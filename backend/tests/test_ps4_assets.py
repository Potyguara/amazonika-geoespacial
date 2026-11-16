"""Testes de ingestão PS4: isolamento e integridade, sem banco de dados."""
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.services.ps4_assets import (
    exists_matching, store_uploaded_asset, stored_file_path,
)


class PS4AssetsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.user_id = uuid4()
        self.piece_id = uuid4()
        self.settings_patch = patch(
            "app.services.ps4_assets.get_settings",
            return_value=SimpleNamespace(storage_dir=Path(self.tmp.name)),
        )
        self.settings_patch.start()

    def tearDown(self):
        self.settings_patch.stop()
        self.tmp.cleanup()

    def test_pdf_preservado_e_sha_verificado(self):
        pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
        record = store_uploaded_asset(
            io.BytesIO(pdf), self.user_id, self.piece_id, "report",
        )
        self.assertEqual(record["size_bytes"], len(pdf))
        self.assertTrue(exists_matching(self.user_id, self.piece_id, record))
        path = stored_file_path(
            self.user_id, self.piece_id, "report", record["sha256"],
        )
        path.write_bytes(pdf + b"modified")
        self.assertFalse(exists_matching(self.user_id, self.piece_id, record))

    def test_pdf_invalido_rejeitado(self):
        with self.assertRaises(ValueError):
            store_uploaded_asset(
                io.BytesIO(b"not pdf"), self.user_id, self.piece_id, "report",
            )

    def test_raster_nao_tiff_rejeitado(self):
        with self.assertRaises(ValueError):
            store_uploaded_asset(
                io.BytesIO(b"not tiff"), self.user_id, self.piece_id, "raster",
            )

    def test_path_nao_aceita_hash_estranho(self):
        with self.assertRaises(ValueError):
            stored_file_path(
                self.user_id, self.piece_id, "report", "../something",
            )


if __name__ == "__main__":
    unittest.main()
