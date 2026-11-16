"""Fila PS4: persistência, limites e retomada após reinício."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
from uuid import UUID
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from app.services.ps4_inpe_queue import (
    new_job, read_job, save_job, queued_jobs, safe_status, prune_terminal_jobs,
)
from app.workers.ps4_inpe_worker import recover_jobs


class Ps4QueueTests(TestCase):
    def test_job_persiste_em_volume_e_nao_expoe_caminhos(self):
        with TemporaryDirectory() as tmp, patch(
            "app.services.ps4_inpe_queue.get_settings",
            return_value=SimpleNamespace(storage_dir=Path(tmp)),
        ):
            job = new_job(
                uuid4(), uuid4(),
                "CBERS4A_WPM_PCA_RGB321_20260410_196_132",
                "CB4A-WPM-PCA-FUSED-1",
                (-51.001, 0.0, -51.0, 0.001),
            )
            save_job(job)
            recovered = read_job(UUID(job["id"]))
            self.assertEqual(recovered["status"], "QUEUED")
            self.assertEqual(len(queued_jobs()), 1)
            self.assertNotIn("bbox", safe_status(recovered))
            self.assertNotIn("user_id", safe_status(recovered))

    def test_limpeza_preserva_jobs_ativos_e_apaga_apenas_status_antigo(self):
        with TemporaryDirectory() as tmp, patch(
            "app.services.ps4_inpe_queue.get_settings",
            return_value=SimpleNamespace(storage_dir=Path(tmp)),
        ):
            now = datetime(2026, 11, 16, tzinfo=timezone.utc)
            old = (now-timedelta(days=120)).isoformat()
            jobs = []
            for status in ("READY", "FAILED", "CANCELLED", "QUEUED", "PROCESSING"):
                job = new_job(
                    uuid4(), uuid4(),
                    "CBERS4A_WPM_PCA_RGB321_20260410_196_132",
                    "CB4A-WPM-PCA-FUSED-1", (-51.001, 0.0, -51.0, 0.001),
                )
                job.update(status=status, finished_at=old)
                save_job(job)
                jobs.append(job)
            self.assertEqual(prune_terminal_jobs(days=90, now=now), 3)
            for job in jobs[:3]:
                with self.assertRaises(FileNotFoundError):
                    read_job(UUID(job["id"]))
            for job in jobs[3:]:
                self.assertEqual(read_job(UUID(job["id"]))["status"], job["status"])

    def test_retencao_minima_protegida(self):
        with self.assertRaisesRegex(ValueError, "30 dias"):
            prune_terminal_jobs(days=7)

    def test_reiniciado_resulta_failed_reprocessavel(self):
        with TemporaryDirectory() as tmp, patch(
            "app.services.ps4_inpe_queue.get_settings",
            return_value=SimpleNamespace(storage_dir=Path(tmp)),
        ):
            job = new_job(
                uuid4(), uuid4(),
                "CBERS4A_WPM_PCA_RGB321_20260410_196_132",
                "CB4A-WPM-PCA-FUSED-1",
                (-51.001, 0.0, -51.0, 0.001),
            )
            job["status"] = "PROCESSING"
            save_job(job)
            recover_jobs()
            from uuid import UUID
            result = read_job(UUID(job["id"]))
            self.assertEqual(result["status"], "FAILED")
            self.assertIsNotNone(result["finished_at"])
