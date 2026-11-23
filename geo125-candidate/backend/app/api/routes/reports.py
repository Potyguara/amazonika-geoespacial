from html import escape
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.analysis import Analysis
from app.models.auth import User
from app.models.report import ReportEmission
from app.services.auth import require_permission
from app.services.territorial_report import issue_territorial_report


router = APIRouter(
    prefix="/reports",
    tags=["Relatórios"],
)


def _authorized_analysis(
    db: Session,
    analysis_id: UUID,
    current_user: User,
) -> Analysis:
    analysis = db.get(
        Analysis,
        analysis_id,
    )

    if not analysis:
        raise HTTPException(
            404,
            "Análise não encontrada.",
        )

    roles = {
        role.code
        for role in current_user.roles
    }

    if (
        "ADMINISTRADOR" not in roles
        and analysis.created_by_user_id != current_user.id
    ):
        raise HTTPException(
            404,
            "Análise não encontrada.",
        )

    return analysis


@router.get(
    "/analyses/{analysis_id}/pdf",
    dependencies=[
        Depends(
            require_permission(
                "analysis.export"
            )
        )
    ],
)
def issue_analysis_pdf(
    analysis_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_permission(
            "analysis.export"
        )
    ),
):
    analysis = _authorized_analysis(
        db,
        analysis_id,
        current_user,
    )

    try:
        emission = issue_territorial_report(
            db,
            analysis,
            current_user,
        )
    except ValueError as exc:
        raise HTTPException(
            422,
            str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            500,
            (
                "Não foi possível gerar o relatório "
                "territorial."
            ),
        ) from exc

    path = Path(
        emission.pdf_path or ""
    )

    if not path.exists():
        raise HTTPException(
            500,
            "PDF gerado não foi localizado.",
        )

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=(
            f"RELATORIO_TERRITORIAL_"
            f"{emission.tracking_code}.pdf"
        ),
        headers={
            "X-Report-Tracking-Code":
                emission.tracking_code,
            "X-Report-SHA256":
                emission.pdf_sha256 or "",
            "Cache-Control": "no-store",
        },
    )


@router.get(
    "/verify/{public_token}",
    response_class=HTMLResponse,
)
def verify_report(
    public_token: str,
    db: Session = Depends(get_db),
):
    emission = db.scalar(
        select(
            ReportEmission
        ).where(
            ReportEmission.public_token
            == public_token
        )
    )

    if not emission:
        raise HTTPException(
            404,
            "Documento não localizado.",
        )

    snapshot = (
        emission.analysis_snapshot or {}
    )

    issuer = (
        snapshot.get("issuer") or {}
    )

    analysis_name = escape(
        str(
            snapshot.get(
                "analysis_name",
                emission.analysis_name,
            )
        )
    )

    tracking = escape(
        emission.tracking_code
    )

    sha256 = escape(
        emission.pdf_sha256 or "—"
    )

    issuer_name = escape(
        str(
            issuer.get(
                "name",
                "Não identificado",
            )
        )
    )

    issued_at = escape(
        str(
            snapshot.get(
                "issued_at",
                emission.issued_at,
            )
        )
    )

    status_label = (
        "DOCUMENTO AUTÊNTICO"
        if emission.status == "READY"
        else escape(emission.status)
    )

    download = (
        f"/api/v1/reports/download/"
        f"{escape(public_token)}"
    )

    return HTMLResponse(
        f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Verificação {tracking}</title>
<style>
body {{
  margin:0;
  background:#eef4f1;
  color:#1e3b30;
  font-family:Arial,sans-serif;
}}
main {{
  max-width:720px;
  margin:40px auto;
  padding:28px;
  background:white;
  border-radius:18px;
  box-shadow:0 18px 55px rgba(18,48,38,.16);
}}
.brand {{
  color:#0d6847;
  font-size:13px;
  font-weight:800;
  letter-spacing:.06em;
}}
.status {{
  display:inline-block;
  margin:20px 0;
  padding:8px 12px;
  border-radius:999px;
  background:#e9f7ef;
  color:#17633f;
  font-weight:800;
}}
dl {{
  display:grid;
  grid-template-columns:180px 1fr;
  gap:10px;
}}
dt {{
  color:#6a7f76;
  font-size:12px;
}}
dd {{
  margin:0;
  font-weight:700;
  overflow-wrap:anywhere;
}}
.hash {{
  font-family:monospace;
  font-size:11px;
}}
a {{
  display:inline-block;
  margin-top:22px;
  padding:12px 18px;
  border-radius:9px;
  background:#0d6847;
  color:white;
  text-decoration:none;
  font-weight:800;
}}
.note {{
  margin-top:24px;
  color:#64786f;
  font-size:12px;
  line-height:1.45;
}}
@media(max-width:600px) {{
  main {{ margin:15px; padding:20px; }}
  dl {{ grid-template-columns:1fr; gap:4px; }}
  dd {{ margin-bottom:10px; }}
}}
</style>
</head>
<body>
<main>
<div class="brand">AMAZONIKA GEOESPACIAL</div>
<h1>Verificação de documento</h1>
<div class="status">{status_label}</div>

<dl>
<dt>Código de rastreio</dt>
<dd>{tracking}</dd>

<dt>Análise</dt>
<dd>{analysis_name}</dd>

<dt>Usuário emissor</dt>
<dd>{issuer_name}</dd>

<dt>Data/hora da emissão</dt>
<dd>{issued_at}</dd>

<dt>SHA-256 do PDF</dt>
<dd class="hash">{sha256}</dd>
</dl>

{
    f'<a href="{download}">Baixar relatório registrado</a>'
    if emission.status == "READY"
    else ""
}

<p class="note">
Esta página confirma o registro da emissão no
Amazonika Geoespacial. O código QR constante no PDF
é vinculado a esta emissão específica.
</p>
</main>
</body>
</html>"""
    )


@router.get(
    "/download/{public_token}",
)
def public_report_download(
    public_token: str,
    db: Session = Depends(get_db),
):
    emission = db.scalar(
        select(
            ReportEmission
        ).where(
            ReportEmission.public_token
            == public_token
        )
    )

    if (
        not emission
        or emission.status != "READY"
    ):
        raise HTTPException(
            404,
            "Documento não disponível.",
        )

    path = Path(
        emission.pdf_path or ""
    )

    if not path.exists():
        raise HTTPException(
            404,
            "Arquivo não disponível.",
        )

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=(
            f"RELATORIO_TERRITORIAL_"
            f"{emission.tracking_code}.pdf"
        ),
        headers={
            "Cache-Control": "private, no-cache",
        },
    )
