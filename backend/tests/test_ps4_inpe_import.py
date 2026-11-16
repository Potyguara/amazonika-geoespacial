"""Testes de segurança e proveniência para importação automática CBERS-4A."""
from tempfile import TemporaryDirectory
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch, MagicMock
from uuid import uuid4
import json
import os
import time

from app.services.inpe_ps4_import import (
    COLLECTION, L4_COLLECTION, _allowed_asset_url,
    fetch_inpe_item, examine_inpe_item, validate_crop,
    fetch_official_xml, verified_official_xml_path, import_inpe_crop,
    cleanup_stale_crop_temporaries,
)


def scene(collection=COLLECTION):
    l4 = collection == L4_COLLECTION
    return {
        "id": ("CBERS_4A_WPM_20260410_196_132_L4" if l4
               else "CBERS4A_WPM_PCA_RGB321_20260410_196_132"),
        "collection": collection,
        "properties": {"datetime": "2026-04-10T00:00:00Z", "gsd": 2},
        "assets": {
            ("BAND0" if l4 else "tci"): {
                "href": "https://data.inpe.br/imagery/original.tif",
                "type": "image/tiff",
            },
            "BAND0.xml": {"href": "https://data.inpe.br/imagery/meta.xml"},
        },
    }


class FakeResponse:
    def __init__(self, url: str, payload: dict):
        self.url, self.payload = url, payload
    def geturl(self):
        return self.url
    def read(self, length=None):
        return json.dumps(self.payload).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


class Ps4InpeImportTests(TestCase):
    def test_metadata_xml_arquivado_com_sha_e_sem_acuracia_automatica(self):
        item = scene(L4_COLLECTION)
        xml = b'<?xml version="1.0"?><Scene><GeometricRMSE>1.7</GeometricRMSE></Scene>'
        item["assets"]["BAND0.xml"] = {
            "href": "https://data.inpe.br/imagery/metadata.xml",
        }
        class XmlResponse:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def geturl(self): return "https://data.inpe.br/imagery/metadata.xml"
            def read(self, limit=None): return xml
        uid, pid = uuid4(), uuid4()
        with TemporaryDirectory() as directory:
            with (
                patch("app.services.inpe_ps4_import.urlopen",
                      return_value=XmlResponse()),
                patch("app.services.inpe_ps4_import.get_settings",
                      return_value=SimpleNamespace(storage_dir=Path(directory))),
            ):
                result = fetch_official_xml(item, uid, pid)
                self.assertEqual(result["status"], "ARCHIVED_UNVERIFIED")
                self.assertFalse(result["absolute_accuracy_verified"])
                self.assertIn("GeometricRMSE", result["candidate_field_names"])
                path = verified_official_xml_path(uid, pid, result)
                self.assertEqual(path.read_bytes(), xml)
                path.write_bytes(b"tampered")
                with self.assertRaisesRegex(ValueError, "Integridade"):
                    verified_official_xml_path(uid, pid, result)

    def test_item_rgb_e_l4_sem_certificacao_automatica(self):
        for collection in (COLLECTION, L4_COLLECTION):
            with self.subTest(collection=collection):
                info = examine_inpe_item(scene(collection))
                self.assertTrue(info["import_supported"])
                self.assertFalse(info["absolute_accuracy_verified"])
                self.assertIsNone(info["orthorectification_rms_m"])
                self.assertFalse(info["report_available"])
                self.assertEqual(info["metadata_assets"], ["BAND0.xml"])

    def test_limpa_somente_temporarios_gdal_antigos(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / ".amazonika-inpe-old"
            recent = root / ".amazonika-inpe-recent"
            evidence = root / "ps4"
            for path in (old, recent, evidence):
                path.mkdir()
                (path / "raster.tif").write_bytes(b"sample")
            ancient = time.time() - 10_000
            os.utime(old, (ancient, ancient))
            with patch("app.services.inpe_ps4_import.get_settings",
                       return_value=SimpleNamespace(storage_dir=root)):
                self.assertEqual(cleanup_stale_crop_temporaries(), 1)
            self.assertFalse(old.exists())
            self.assertTrue(recent.exists())
            self.assertTrue(evidence.exists())

    def test_recorte_bloqueado_com_espaco_insuficiente(self):
        item = scene()
        with TemporaryDirectory() as directory:
            with (
                patch("app.services.inpe_ps4_import.get_settings",
                      return_value=SimpleNamespace(storage_dir=Path(directory))),
                patch("app.services.inpe_ps4_import.shutil.disk_usage",
                      return_value=SimpleNamespace(free=1 * 1024**3)),
                patch("app.services.inpe_ps4_import.subprocess.run") as gdal,
            ):
                with self.assertRaisesRegex(RuntimeError, "2 GiB"):
                    import_inpe_crop(
                        item, (-51.001, 0.0, -51.0, 0.001), uuid4(), uuid4(),
                    )
                gdal.assert_not_called()

    def test_recorte_pequeno_em_utm(self):
        epsg, res = validate_crop((-51.01, 0.01, -51.0, 0.02))
        self.assertEqual(epsg, 32622)
        self.assertEqual(res, 2.0)

    def test_recorte_excessivo_bloqueado(self):
        with self.assertRaisesRegex(ValueError, "maior"):
            validate_crop((-51.5, 0.01, -51.0, 0.02))

    def test_urls_externas_e_protocolo_nao_sao_aceitos(self):
        for url in (
            "http://data.inpe.br/file.tif",
            "https://localhost/file.tif",
            "https://127.0.0.1/file.tif",
            "https://data.inpe.br.evil.example/file.tif",
            "https://data.inpe.br@evil.example/file.tif",
            "https://data.inpe.br/file.xml",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                _allowed_asset_url(url)

    def test_item_de_outra_colecao_bloqueado(self):
        with self.assertRaises(ValueError):
            fetch_inpe_item("CBERS4A_WPM_PCA_RGB321_20260410_196_132",
                            "NOT-A-COLLECTION")

    def test_resposta_stac_id_diferente_e_rejeitada(self):
        item = scene()
        item["id"] = "OTHER"
        with patch(
            "app.services.inpe_ps4_import.urlopen",
            side_effect=lambda request, timeout: FakeResponse(
                request.full_url, item
            ),
        ):
            with self.assertRaisesRegex(ValueError, "não corresponde"):
                fetch_inpe_item("CBERS4A_WPM_PCA_RGB321_20260410_196_132")

    def test_busca_stac_somente_host_fixo(self):
        item = scene(L4_COLLECTION)
        with patch(
            "app.services.inpe_ps4_import.urlopen",
            side_effect=lambda request, timeout: FakeResponse(
                request.full_url, item
            ),
        ) as mocked:
            result = fetch_inpe_item(item["id"], L4_COLLECTION)
        self.assertEqual(result["id"], item["id"])
        self.assertIn("https://data.inpe.br/bdc/stac/v1/", mocked.call_args.args[0].full_url)
