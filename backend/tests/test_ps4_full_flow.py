"""Fluxo PS4 end-to-end em memória: GeoTIFF real -> PDF -> V -> RT -> tiles."""
from io import BytesIO
from pathlib import Path
from shutil import which
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, skipUnless
from unittest.mock import patch
from uuid import uuid4
import subprocess

from fastapi import UploadFile
from PIL import Image
from starlette.requests import Request

from app.api.routes.technical_pieces import (
    PS4RTAttestation, approve_ps4, get_ps4, ps4_raster_tile,
    save_ps4, upload_ps4_file,
)
from app.services.ps4_validation import PS4Submission


class DummyDb:
    def add(self, _): pass
    def commit(self): pass
    def refresh(self, _): pass


@skipUnless(all(which(x) for x in ("gdalinfo", "gdal_translate", "gdalwarp")),
            "GDAL CLI requerido")
class PS4FullFlowTests(TestCase):
    def test_full_flow_without_external_network(self):
        with TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            rgb = temp / "rgb.png"
            tif = temp / "source.tif"
            Image.new("RGB", (90, 90), (52, 107, 156)).save(rgb)
            subprocess.run([
                "gdal_translate", "-q", "-of", "GTiff",
                "-a_srs", "EPSG:4326", "-a_ullr", "-52", "1", "-50", "-1",
                str(rgb), str(tif),
            ], check=True)

            user = SimpleNamespace(
                id=uuid4(), full_name="RT DE TESTE",
                professional_profile_json={"crea":"CREA-TESTE","art":"ART-TESTE"},
            )
            vertex = {"name":"PS4-V-001", "longitude":-51.0,
                      "latitude":0.1, "scene_id":"SCENE-TEST"}
            piece = SimpleNamespace(
                id=uuid4(), status="DRAFT",
                snapshot={"topcon":{"ps4_draft":[vertex]}},
            )
            db = DummyDb()
            request = Request({
                "type":"http", "method":"POST", "path":"/test", "headers":[],
            })
            settings = SimpleNamespace(storage_dir=temp)
            report = b"%PDF-1.4\n1 0 obj\n<< >>\nendobj\n%%EOF\n"
            with (
                patch("app.api.routes.technical_pieces._owned", return_value=piece),
                patch("app.services.ps4_assets.get_settings", return_value=settings),
                patch("app.api.routes.technical_pieces.write_audit"),
            ):
                raster_upload = UploadFile(
                    filename="ortho.tif", file=BytesIO(tif.read_bytes())
                )
                raster = upload_ps4_file(
                    piece.id, "raster", raster_upload, db, user
                )["asset"]
                report_upload = UploadFile(
                    filename="relatorio.pdf", file=BytesIO(report)
                )
                report_asset = upload_ps4_file(
                    piece.id, "report", report_upload, db, user
                )["asset"]
                submission = PS4Submission.model_validate({
                    "needs_additional_vertices":True,
                    "evidence":{
                        "scene_id":"SCENE-TEST", "report_scene_id":"SCENE-TEST",
                        "raster_sha256":raster["sha256"],
                        "report_sha256":report_asset["sha256"],
                        "orthorectification_rms_m":1.0,
                        "horizontal_positional_precision_m":2.0,
                        "gsd_m":2.0, "scene_crs":"EPSG:4326",
                        "feature_identifiable":True,
                    },
                    "vertices":[{
                        "vertex_id":"PS4-V-001", "longitude":-51.0,
                        "latitude":0.1, "limit_type":"natural",
                        "feature_type":"natural_feature",
                    }],
                })
                saved = save_ps4(piece.id, submission, db, user)
                self.assertEqual(saved["ps4"]["validation"]["status"],
                                 "REVIEW_REQUIRED")
                checks = PS4RTAttestation(**{
                    field: True for field in PS4RTAttestation.model_fields
                })
                approved = approve_ps4(
                    piece.id, checks, request, db, user,
                )
                self.assertEqual(
                    approved["ps4"]["validation"]["status"], "APPROVED_BY_RT",
                )
                restored = get_ps4(piece.id, db, user)
                self.assertEqual(restored["approval"]["rt_name"], "RT DE TESTE")
                tile = ps4_raster_tile(
                    piece.id, raster["sha256"], 10, 366, 511, db, user,
                )
                self.assertEqual(tile.media_type, "image/png")
                self.assertTrue(tile.body.startswith(b"\x89PNG\r\n\x1a\n"))
                self.assertEqual(tile.headers.get("x-ps4-raster-sha256"),
                                 raster["sha256"])
