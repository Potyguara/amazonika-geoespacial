"""Worker isolado para recortes CBERS; executado pelo package-worker existente."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.technical_piece import TechnicalPiece
from app.services.inpe_ps4_import import fetch_inpe_item, import_inpe_crop
from app.services.ps4_validation import PS4Submission, evaluate_verified_ps4
from app.services.ps4_inpe_queue import (
    read_job, save_job, queued_jobs, jobs_root,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def recover_jobs() -> None:
    """Após reinício, marca processing como falha; não duplica processamento."""
    for path in jobs_root().glob("*.json"):
        try:
            job = read_job(UUID(path.stem))
            if job.get("status") == "PROCESSING":
                job.update(status="FAILED", finished_at=_now(),
                           message="Worker reiniciado durante o recorte; reenvie a solicitação.")
                save_job(job)
        except (OSError, ValueError, KeyError):
            pass


def process_job(job_path) -> None:
    job = read_job(UUID(job_path.stem))
    if job.get("status") != "QUEUED":
        return
    job_id = str(job["id"])
    user_id, piece_id = UUID(job["user_id"]), UUID(job["piece_id"])
    db = SessionLocal()
    try:
        # Nunca processar jobs obsoletos nem peças de outro usuário.
        piece = db.scalar(select(TechnicalPiece).where(
            TechnicalPiece.id == piece_id, TechnicalPiece.user_id == user_id,
        ))
        current = ((piece.snapshot or {}).get("ps4") or {}) if piece else {}
        if current.get("import_job_id") != job_id:
            job.update(status="CANCELLED", finished_at=_now(),
                       message="Solicitação substituída ou peça indisponível.")
            save_job(job)
            return
        job.update(status="PROCESSING", started_at=_now(),
                   message="Obtendo recorte do catálogo oficial INPE.")
        save_job(job)
        item = fetch_inpe_item(job["item_id"], job["collection"])
        # Verificação geográfica no worker (não confiar só no enfileiramento).
        from shapely.geometry import shape, box
        footprint = shape(item.get("geometry"))
        if footprint.is_empty or not footprint.is_valid or not footprint.covers(
            box(*job["bbox"])
        ):
            raise ValueError("Recorte fora da cobertura da cena selecionada.")
        result = import_inpe_crop(
            item, tuple(job["bbox"]), user_id, piece_id,
        )
        # Lock em linha garante que um salvamento concorrente não será sobrescrito.
        piece = db.scalar(
            select(TechnicalPiece).where(
                TechnicalPiece.id == piece_id,
                TechnicalPiece.user_id == user_id,
            ).with_for_update()
        )
        if piece is None:
            raise ValueError("Peça técnica removida.")
        snapshot = dict(piece.snapshot or {})
        ps4 = dict(snapshot.get("ps4") or {})
        if ps4.get("import_job_id") != job_id:
            job.update(status="CANCELLED", finished_at=_now(),
                       message="Solicitação substituída; resultado descartado.")
            save_job(job)
            db.rollback()
            return
        # Novo raster exige novas evidências e nova aprovação humana.
        ps4["assets"] = {"raster": result["asset"]}
        ps4["source_provenance"] = result["provenance"]
        ps4.pop("approval", None)
        ps4.pop("completed_at", None)
        if "submission" in ps4:
            ps4["validation"] = evaluate_verified_ps4(
                PS4Submission.model_validate(ps4["submission"]),
                ps4["assets"], user_id, piece_id,
            )
        snapshot["ps4"] = ps4
        piece.snapshot = snapshot
        piece.status = "DRAFT"
        db.add(piece)
        db.commit()
        job.update(
            status="READY", finished_at=_now(),
            message="GeoTIFF do INPE pronto. Relatório e aprovação RT ainda obrigatórios.",
        )
        save_job(job)
    except Exception as exc:
        db.rollback()
        # Não expor URLs/caminhos internos ao navegador. Erro completo fica no log.
        print(f"[ps4-inpe-worker] FAILED job={job_id} {type(exc).__name__}: {exc}", flush=True)
        job.update(
            status="FAILED", finished_at=_now(),
            message="Não foi possível preparar a imagem. Verifique a cena e tente novamente.",
        )
        save_job(job)
    finally:
        db.close()


def process_next_job() -> bool:
    jobs = queued_jobs()
    if not jobs:
        return False
    process_job(jobs[0])
    return True
