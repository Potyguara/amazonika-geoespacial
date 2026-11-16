"""Worker isolado para recortes CBERS; executado pelo package-worker existente."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.technical_piece import TechnicalPiece
from app.services.inpe_ps4_import import fetch_inpe_item, import_inpe_crop
from app.services.ps4_assets import stored_file_path
from app.core.config import get_settings
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


def _remove_replaced_assets(user_id, piece_id, old_ps4: dict, new_result: dict) -> None:
    """Remove SOMENTE o recorte antigo após commit da substituição concluída."""
    old_raster = (old_ps4.get("assets") or {}).get("raster") or {}
    old_digest = old_raster.get("sha256")
    new_digest = new_result["asset"]["sha256"]
    if isinstance(old_digest, str) and old_digest != new_digest:
        try:
            stored_file_path(user_id, piece_id, "raster", old_digest).unlink(missing_ok=True)
        except (OSError, ValueError) as exc:
            print(f"[ps4-inpe-worker] aviso limpeza raster antigo: {type(exc).__name__}", flush=True)
    # O novo recorte não herda o laudo PDF da cena anterior.
    old_report = (old_ps4.get("assets") or {}).get("report") or {}
    old_report_digest = old_report.get("sha256")
    if isinstance(old_report_digest, str):
        try:
            stored_file_path(user_id, piece_id, "report", old_report_digest).unlink(missing_ok=True)
        except (OSError, ValueError) as exc:
            print(f"[ps4-inpe-worker] aviso limpeza PDF antigo: {type(exc).__name__}", flush=True)
    old_xml = ((old_ps4.get("source_provenance") or {}).get("technical_xml") or {})
    new_xml = ((new_result["provenance"].get("technical_xml") or {}))
    old_xml_digest = old_xml.get("sha256")
    if (isinstance(old_xml_digest, str) and old_xml_digest != new_xml.get("sha256")
        and len(old_xml_digest) == 64
        and all(c in "0123456789abcdef" for c in old_xml_digest)):
        path = (get_settings().storage_dir / "ps4" / str(user_id) / str(piece_id)
                / f"inpe-metadata-{old_xml_digest}.xml")
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            print(f"[ps4-inpe-worker] aviso limpeza XML antigo: {type(exc).__name__}", flush=True)


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
        # Fecha a transação de leitura antes do processamento GDAL remoto.
        # A transação com lock é iniciada somente quando o resultado estiver pronto.
        db.rollback()
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
        # Preservar identificadores antigos só até o novo commit ter sucesso.
        previous_ps4 = dict(ps4)
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
        _remove_replaced_assets(user_id, piece_id, previous_ps4, result)
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
