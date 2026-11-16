"""Regressões do worker PS4: isolamento de jobs, concorrência e conclusão."""
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4


from app.workers.ps4_inpe_worker import process_job


class FakeDB:
    def __init__(self, piece):
        self.piece = piece
        self.commits = 0
    def scalar(self, _query):
        return self.piece
    def add(self, _): pass
    def commit(self):
        self.commits += 1
    def rollback(self): pass
    def close(self): pass


class Ps4WorkerTests(TestCase):
    def setUp(self):
        self.uid = uuid4()
        self.pid = uuid4()
        self.jid = uuid4()
        self.piece = SimpleNamespace(
            id=self.pid, user_id=self.uid, status="DRAFT",
            snapshot={"ps4": {"import_job_id": str(self.jid), "assets": {
                "report": {"sha256": "c"*64, "kind": "report"}
            }, "approval": {"status": "APPROVED_BY_RT"}}},
        )
        self.db = FakeDB(self.piece)
        self.job = {
            "id": str(self.jid), "user_id": str(self.uid), "piece_id": str(self.pid),
            "item_id": "CBERS4A_WPM_PCA_RGB321_20260410_196_132",
            "collection": "CB4A-WPM-PCA-FUSED-1",
            "bbox": [-51.01, 0.0, -51.0, 0.01],
            "status": "QUEUED",
        }
        self.item = {
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-52, -1], [-50, -1], [-50, 1], [-52, 1], [-52, -1],
                ]],
            },
        }

    def test_job_obsoleto_cancelado_sem_gdal(self):
        self.piece.snapshot["ps4"]["import_job_id"] = str(uuid4())
        saved = []
        with (
            patch("app.workers.ps4_inpe_worker.read_job",
                  return_value=dict(self.job)),
            patch("app.workers.ps4_inpe_worker.save_job",
                  side_effect=lambda job: saved.append(dict(job))),
            patch("app.workers.ps4_inpe_worker.SessionLocal",
                  return_value=self.db),
            patch("app.workers.ps4_inpe_worker.import_inpe_crop") as importer,
        ):
            process_job(Path(str(self.jid) + ".json"))
        self.assertEqual(saved[-1]["status"], "CANCELLED")
        self.assertEqual(self.db.commits, 0)
        importer.assert_not_called()

    def test_success_vincula_somente_novo_raster_e_exige_rt(self):
        saved = []
        with (
            patch("app.workers.ps4_inpe_worker.read_job",
                  return_value=dict(self.job)),
            patch("app.workers.ps4_inpe_worker.save_job",
                  side_effect=lambda job: saved.append(dict(job))),
            patch("app.workers.ps4_inpe_worker.SessionLocal",
                  return_value=self.db),
            patch("app.workers.ps4_inpe_worker.fetch_inpe_item",
                  return_value=self.item),
            patch("app.workers.ps4_inpe_worker.import_inpe_crop",
                  return_value={
                      "asset": {"kind": "raster", "sha256": "a"*64},
                      "provenance": {"item_id": self.job["item_id"],
                                     "requires_rt_review": True},
                  }),
        ):
            process_job(Path(str(self.jid)+".json"))
        self.assertEqual(saved[-1]["status"], "READY")
        self.assertEqual(self.db.commits, 1)
        ps4 = self.piece.snapshot["ps4"]
        self.assertEqual(ps4["assets"], {
            "raster": {"kind": "raster", "sha256": "a"*64}
        })
        self.assertNotIn("approval", ps4)
        self.assertEqual(ps4["source_provenance"]["item_id"], self.job["item_id"])
