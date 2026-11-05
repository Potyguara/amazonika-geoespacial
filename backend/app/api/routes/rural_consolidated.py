"""Standalone FULL FARM consolidated report endpoints.

Does not modify /reports/analyses/{id}/pdf (territorial report).
Only previously completed polygon analyses may be used in this first stage.
"""
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.analysis import Analysis
from app.models.auth import User
from app.models.rural_consolidated import RuralConsolidatedJob
from app.services.auth import require_permission
from app.services.rural_consolidated import run_consolidated_job

router = APIRouter(
    prefix="/rural-consolidated",
    tags=["Relatório Consolidado da Fazenda"],
    dependencies=[Depends(require_permission("analysis.view"))],
)


def _can_access(user: User, job: RuralConsolidatedJob) -> bool:
    return user.id == job.created_by_user_id or any(
        role.code == "ADMINISTRADOR" for role in user.roles
    )


@router.post("/analyses/{analysis_id}", status_code=202,
             dependencies=[Depends(require_permission("analysis.execute"))])
def create_consolidated_report(
    analysis_id: UUID,
    tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("analysis.execute")),
):
    analysis = db.get(Analysis, analysis_id)
    if not analysis or (
        analysis.created_by_user_id != user.id
        and not any(role.code == "ADMINISTRADOR" for role in user.roles)
    ):
        raise HTTPException(404, "Análise de origem não encontrada.")
    if analysis.status != "COMPLETED" or analysis.geometry_kind not in {"POLYGON", "MULTIPOLYGON"}:
        raise HTTPException(409, "Relatório consolidado exige polígono e análise de origem concluída.")
    job = RuralConsolidatedJob(
        source_analysis_id=analysis.id,
        created_by_user_id=user.id,
        status="QUEUED",
        progress_percent=0,
        snapshot_json={},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    tasks.add_task(run_consolidated_job, job.id)
    return {
        "job_id": str(job.id), "status": "QUEUED", "progress_percent": 0,
        "report_type": "FULL_FARM_CONSOLIDATED",
        "report_stage": "PRELIMINARY_PARTIAL",
        "message": "Prévia consolidada: outras fontes temáticas ainda não são consultadas nesta versão.",
    }


@router.get("/jobs/{job_id}")
def consolidated_job_status(
    job_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("analysis.view")),
):
    job = db.get(RuralConsolidatedJob, job_id)
    if not job or not _can_access(user, job):
        raise HTTPException(404, "Relatório não encontrado.")
    return {
        "job_id": str(job.id),
        "source_analysis_id": str(job.source_analysis_id),
        "report_type": job.report_type,
        "report_stage": "PRELIMINARY_PARTIAL",
        "status": job.status,
        "progress_percent": job.progress_percent,
        "sections": (job.snapshot_json or {}).get("sections", []),
        "pdf_ready": bool(job.status == "COMPLETED" and job.pdf_relative_path),
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "error_message": "Falha no processamento do consolidado." if job.status == "FAILED" else None,
    }


@router.get("/jobs/{job_id}/pdf",
            dependencies=[Depends(require_permission("analysis.export"))])
def download_consolidated_pdf(
    job_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("analysis.export")),
):
    job = db.get(RuralConsolidatedJob, job_id)
    if not job or not _can_access(user, job):
        raise HTTPException(404, "Relatório não encontrado.")
    if job.status != "COMPLETED" or not job.pdf_relative_path:
        raise HTTPException(409, "PDF ainda não está disponível.")
    if job.pdf_relative_path != str(job.id) + ".pdf":
        raise HTTPException(500, "Registro do PDF inconsistente.")
    file = Path(get_settings().storage_dir).resolve() / "rural-consolidated" / job.pdf_relative_path
    if not file.is_file() or sha256(file.read_bytes()).hexdigest() != job.pdf_sha256:
        raise HTTPException(503, "Arquivo PDF indisponível ou integridade inválida.")
    return FileResponse(
        file, media_type="application/pdf",
        filename=f"AMAZONIKA_CONSOLIDADO_PRELIMINAR_{job.id.hex[:12]}.pdf",
        headers={
            "Cache-Control": "no-store, private",
            "X-Report-Type": "full-farm-consolidated-preliminary-partial",
            "X-Report-SHA256": job.pdf_sha256,
        },
    )
