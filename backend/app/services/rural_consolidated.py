"""First operational full-farm consolidation: immutable evidence from existing analysis.

No upstream calls, no fake findings, no paid services. Separate job and PDF
from the existing territorial report. Background processing stores a frozen
source snapshot, then builds a clearly marked *partial* consolidated report.
"""
from datetime import datetime, timezone
from copy import deepcopy
from hashlib import sha256
from html import escape
from io import BytesIO
import json
from pathlib import Path
from uuid import UUID

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    KeepTogether, HRFlowable,
)
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.analysis import Analysis, AnalysisResult
from app.models.catalog import Source, SourceVersion
from app.models.rural_consolidated import RuralConsolidatedJob
from app.schemas.rural_consolidated import SectionCode, SectionStatus, status_label
from app.services.rural_ibama_embargos import embargo_preview, IbamaEmbargoError
from app.services.rural_monitoring import monitoring_preview, MonitoringQueryError

FOREST = colors.HexColor("#123F30")
MINT = colors.HexColor("#EAF1EC")
TEXT = colors.HexColor("#233C32")
GREY = colors.HexColor("#64786F")
THEMES = [
    (SectionCode.IDENTIFICATION, "Identificação cadastral"),
    (SectionCode.TERRITORIAL_OVERLAYS, "Sobreposições territoriais"),
    (SectionCode.ENVIRONMENTAL_ENFORCEMENT, "Fiscalização ambiental"),
    (SectionCode.DEFORESTATION_ALERTS, "Alertas de desmatamento"),
    (SectionCode.PRODES_DETER, "Monitoramento PRODES / DETER"),
    (SectionCode.FIRE_SCARS, "Áreas queimadas"),
    (SectionCode.MINING_ANM, "Processos minerários"),
    (SectionCode.LAND_COVER_MAPBIOMAS, "Uso e cobertura do solo"),
    (SectionCode.LAND_USE_APTITUDE, "Aptidão agrícola"),
    (SectionCode.WATER_RESOURCES, "Recursos hídricos"),
    (SectionCode.CULTURAL_HERITAGE_IPHAN, "Patrimônio cultural"),
    (SectionCode.PUBLIC_FORESTS, "Florestas públicas"),
    (SectionCode.INFRASTRUCTURE_LOGISTICS, "Infraestrutura e logística"),
    (SectionCode.TOPOGRAPHY_SLOPE, "Relevo e declividade"),
    (SectionCode.SOILS, "Solos"),
    (SectionCode.PASTURE, "Pastagens"),
    (SectionCode.CLIMATE, "Clima"),
    (SectionCode.METHODOLOGY, "Metodologia"),
]


def _safe(value: object, limit: int = 200) -> str:
    return escape(str(value if value is not None else "Não informado")[:limit])


def build_job_snapshot(db: Session, analysis: Analysis) -> dict:
    """No inference of clean environmental status from 0/0 selected sources."""
    if analysis.status != "COMPLETED" or analysis.geometry_kind not in {"POLYGON", "MULTIPOLYGON"}:
        raise ValueError("Consolidado requer análise poligonal previamente concluída.")
    geojson = db.scalar(
        text("SELECT ST_AsGeoJSON(input_geom, 9) FROM analyses WHERE id=:id"),
        {"id": analysis.id},
    )
    if not geojson:
        raise ValueError("A geometria da análise não está disponível.")
    geometry = json.loads(geojson)
    # Hash stable for frozen geometry and source analysis, independent of UI.
    digest = sha256(json.dumps(geometry, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    statuses = list(analysis.source_status_json or [])
    # Fallback: only already-recorded AnalysisResult rows are proven consulted.
    rows = db.execute(
        select(AnalysisResult, Source, SourceVersion)
        .join(Source, Source.id == AnalysisResult.source_id)
        .join(SourceVersion, SourceVersion.id == AnalysisResult.source_version_id)
        .where(AnalysisResult.analysis_id == analysis.id),
    ).all()
    by_source = {}
    for status in statuses:
        code = str(status.get("source_id", ""))
        by_source[code] = {
            "name": str(status.get("source_name") or "Fonte sem nome")[:180],
            "institution": str(status.get("institution") or "Não informado")[:180],
            "status": str(status.get("status") or "UNAVAILABLE"),
            "reference_date": str(status.get("reference_date") or ""),
            "matched_features": status.get("matched_features"),
            "overlap_hectares": status.get("overlap_hectares"),
            "message": str(status.get("message") or "")[:220],
        }
    for result, source, version in rows:
        by_source[str(source.id)] = {
            "name": source.name, "institution": source.institution,
            "status": "ANALYZED",
            "reference_date": version.reference_date.isoformat() if version.reference_date else "",
            "matched_features": int(result.matched_features or 0),
            "overlap_hectares": float(result.overlap_hectares or 0),
            "message": "",
        }
    sources = sorted(by_source.values(), key=lambda item: (item["status"] != "ANALYZED", item["name"]))
    analyzed = [s for s in sources if s["status"] == "ANALYZED"]
    failures = [s for s in sources if s["status"] != "ANALYZED"]
    hits = [s for s in analyzed if (s["matched_features"] or 0) > 0]
    if not analyzed:
        overlays_status = SectionStatus.NOT_RUN if not sources else SectionStatus.UNAVAILABLE
    else:
        overlays_status = (
            SectionStatus.UNAVAILABLE if failures else
            SectionStatus.COMPLETE if hits else SectionStatus.NO_OCCURRENCE
        )
    sections = [{
        "code": code.value,
        "title": title,
        "status": (overlays_status.value if code == SectionCode.TERRITORIAL_OVERLAYS
                   else SectionStatus.NOT_RUN.value),
        "message": (
            f"{len(analyzed)} base(s) consultada(s), {len(failures)} sem confirmação."
            if code == SectionCode.TERRITORIAL_OVERLAYS else
            "Este tema exige integração e análise própria; não foi executado."
        ),
    } for code, title in THEMES]
    sections[0]["status"] = SectionStatus.COMPLETE.value
    sections[0]["message"] = "Identificação do perímetro extraída da análise original."
    sections[-1]["status"] = SectionStatus.COMPLETE.value
    sections[-1]["message"] = "Metodologia e limitações documentadas nesta emissão preliminar."
    subject = dict(analysis.subject_json or {})
    return {
        "report_type": "FULL_FARM_CONSOLIDATED",
        "report_stage": "PRELIMINARY_PARTIAL",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "property": {
            "name": str(analysis.name)[:180],
            "area_hectares": float(analysis.area_hectares or 0),
            "geometry_kind": analysis.geometry_kind,
            "geometry_crs": "EPSG:4674",
            "geometry_sha256": digest,
            "cadastral_origin": str(subject.get("source_name") or "Geometria de análise")[:120],
            "cadastral_code": str(subject.get("cadastral_code") or subject.get("car_code") or "")[:100] or None,
            "source_analysis_id": str(analysis.id),
        },
        "sections": sections,
        "territorial_evidence": {
            "sources": sources,
            "analyzed_count": len(analyzed),
            "inconclusive_count": len(failures),
            "sources_with_intersections": len(hits),
            "unverified_sources": len(failures),
        },
    }


def analyze_ibama_embargos(snapshot: dict, geometry: dict) -> None:
    """First independent theme: bounded official embargo intersection, fail closed.

    Invoked in background only; no paid API or Google Cloud. Never claim a
    clean result on upstream failure, timeout, oversized bbox or truncation.
    """
    section = next(x for x in snapshot["sections"]
                   if x["code"] == SectionCode.ENVIRONMENTAL_ENFORCEMENT.value)
    section["status"] = SectionStatus.RUNNING.value
    try:
        result = embargo_preview(geometry)
        if result.get("status") != "ANALYZED":
            raise IbamaEmbargoError("Resposta IBAMA inconclusiva.")
        count = result.get("interfering_features")
        if not isinstance(count, int) or count < 0:
            raise IbamaEmbargoError("Contagem IBAMA inconclusiva.")
        section["status"] = (
            SectionStatus.COMPLETE.value if count else SectionStatus.NO_OCCURRENCE.value
        )
        section["message"] = (
            f"{count} polígono(s) de embargo intersectam a área consultada; "
            "a interseção não comprova responsabilidade do detentor."
        ) if count else "Consulta IBAMA concluída sem polígonos de embargo incidentes."
        snapshot["ibama_embargos"] = {
            "source": result.get("source"),
            "layer": result.get("layer"),
            "queried_at": result.get("queried_at"),
            "count": count,
            "overlap_hectares": result.get("overlap_hectares"),
            "overlap_percent": result.get("overlap_percent"),
            "method": result.get("method"),
            "warning": result.get("warning"),
            "features": [
                {
                    "term": row.get("term"),
                    "process": row.get("process"),
                    "overlap_hectares": row.get("overlap_hectares"),
                } for row in result.get("features", [])[:100]
            ],
        }
    except (IbamaEmbargoError, ValueError, TypeError, KeyError) as exc:
        section["status"] = SectionStatus.UNAVAILABLE.value
        section["message"] = (
            "Consulta oficial IBAMA não concluída. Não é possível afirmar "
            "ausência de embargos para este imóvel."
        )
        snapshot["ibama_embargos"] = {
            "status": "UNAVAILABLE",
            "error_category": type(exc).__name__,
        }


def analyze_monitoring(snapshot: dict, geometry: dict, layer_name: str | None) -> None:
    """Only query a preselected TerraBrasilis WFS layer.

    No automatic substitution of a different year or product. The backend
    validates the layer against live official GetCapabilities.
    """
    if not layer_name:
        return
    section = next(x for x in snapshot["sections"]
                   if x["code"] == SectionCode.PRODES_DETER.value)
    section["status"] = SectionStatus.RUNNING.value
    try:
        result = monitoring_preview(layer_name, geometry)
        if result.get("status") != "ANALYZED" or result.get("layer") != layer_name:
            raise MonitoringQueryError("Resposta de monitoramento incompleta.")
        count = result.get("interfering_features")
        if not isinstance(count, int) or count < 0:
            raise MonitoringQueryError("Total de monitoramento inconsistente.")
        section["status"] = (
            SectionStatus.COMPLETE.value if count else SectionStatus.NO_OCCURRENCE.value
        )
        section["message"] = (
            f"{count} feição(ões) incidentes no produto {layer_name}."
            if count else f"Consulta concluída, sem incidências na camada {layer_name}."
        )
        snapshot["monitoring_result"] = {
            "status": "ANALYZED",
            "source": result.get("source"),
            "layer": result.get("layer"),
            "layer_title": result.get("layer_title"),
            "program": result.get("program"),
            "queried_at": result.get("queried_at"),
            "count": count,
            "overlap_hectares": result.get("overlap_hectares"),
            "method": result.get("method"),
            "warning": result.get("warning"),
            "features": [
                {"id": str(row.get("id") or "")[:120],
                 "overlap_hectares": row.get("overlap_hectares")}
                for row in result.get("features", [])[:100]
            ],
        }
    except (MonitoringQueryError, ValueError, TypeError, KeyError) as exc:
        section["status"] = SectionStatus.UNAVAILABLE.value
        section["message"] = (
            "Camada PRODES/DETER indisponível ou consulta incompleta. "
            "Não é possível afirmar ausência de desmatamento."
        )
        snapshot["monitoring_result"] = {
            "status": "UNAVAILABLE", "error_category": type(exc).__name__,
        }


def _page_frame(canvas, doc):
    canvas.saveState()
    w, h = A4
    canvas.setStrokeColor(colors.HexColor("#B8CBC0"))
    canvas.line(18*mm, h-16*mm, w-18*mm, h-16*mm)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(FOREST)
    canvas.drawString(18*mm, h-13*mm, "AMAZONIKA GEOESPACIAL")
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GREY)
    canvas.drawString(18*mm, 13*mm, "Relatório consolidado preliminar | Não substitui documentos oficiais")
    canvas.drawRightString(w-18*mm, 13*mm, f"Página {doc.page}")
    canvas.restoreState()


def render_preliminary_consolidated_pdf(snapshot: dict) -> bytes:
    """Visual milestone: only source-backed fields. No fake satellite imagery."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=18*mm, rightMargin=18*mm,
        topMargin=25*mm, bottomMargin=23*mm,
        title="AMAZONIKA - Relatório Consolidado Preliminar",
        author="Amazonika Geoespacial",
    )
    styles = {
        "h1": ParagraphStyle("h1c", fontName="Helvetica-Bold", fontSize=20,
            leading=26, textColor=FOREST, spaceAfter=10),
        "h2": ParagraphStyle("h2c", fontName="Helvetica-Bold", fontSize=12,
            leading=16, textColor=FOREST, spaceBefore=13, spaceAfter=7),
        "body": ParagraphStyle("bc", fontName="Helvetica", fontSize=9,
            leading=14, textColor=TEXT, spaceAfter=6),
        "small": ParagraphStyle("sc", fontName="Helvetica", fontSize=7.5,
            leading=11, textColor=GREY, spaceAfter=6),
        "table": ParagraphStyle("tc", fontName="Helvetica", fontSize=7.2,
            leading=10, textColor=TEXT),
        "badge": ParagraphStyle("bcc", fontName="Helvetica-Bold", fontSize=8,
            leading=11, textColor=FOREST, alignment=TA_CENTER),
    }
    P = lambda txt, kind="body": Paragraph(txt, styles[kind])
    subject = snapshot["property"]
    ev = snapshot["territorial_evidence"]
    story = [
        Spacer(1, 19*mm),
        P("RELATÓRIO CONSOLIDADO DA PROPRIEDADE RURAL", "h1"),
        P("PRÉVIA PARCIAL — módulos não executados identificados individualmente", "small"),
        HRFlowable(width="100%", thickness=1.3, color=FOREST),
        Spacer(1, 9*mm),
        P(_safe(subject["name"]), "h2"),
    ]
    rows = [
        ("Área geométrica", f'{subject["area_hectares"]:,.4f} ha'),
        ("Referência cadastral", _safe(subject.get("cadastral_code") or "Não informada")),
        ("Origem", _safe(subject["cadastral_origin"])),
        ("SRC", _safe(subject["geometry_crs"])),
        ("Análise territorial original", _safe(subject["source_analysis_id"])),
        ("Geometria SHA-256", _safe(subject["geometry_sha256"], 70)),
    ]
    t = Table([[P(_safe(k),"table"), P(_safe(v),"table")] for k,v in rows],
              colWidths=[52*mm, 120*mm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(0,-1),MINT),
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("BOTTOMPADDING",(0,0),(-1,-1),8),
        ("TOPPADDING",(0,0),(-1,-1),7),
        ("LINEBELOW",(0,0),(-1,-1),0.3,colors.HexColor("#D1DFD5")),
    ]))
    story.extend([t, Spacer(1,10*mm), P("Escopo desta prévia", "h2"),
        P("A estrutura de consolidação está operacional. Esta emissão preliminar "
          "reutiliza evidências de sobreposição já registradas e pode consultar "
          "separadamente embargos IBAMA e uma camada INPE explicitamente selecionada. "
          "MapBiomas, solos, clima e demais temas permanecem não executados."),
        P("Não há imagem de satélite nem mapa temático neste marco inicial. "
          "Eles serão incluídos somente com imagens e geodados reais, "
          "metodologia verificada e orçamento de processamento aprovado.", "small"),
        PageBreak(),
        P("SUMÁRIO DE COBERTURA ANALÍTICA", "h1"),
        P("Cada tema indica explicitamente seu estado, sem presumir ausência de ocorrências.", "small"),
    ])
    theme_rows = [[P("Tema","table"),P("Situação","table")]]
    for sec in snapshot["sections"]:
        theme_rows.append([P(_safe(sec["title"]),"table"),
                           P(_safe(status_label(SectionStatus(sec["status"]))),"table")])
    tab = Table(theme_rows,colWidths=[96*mm,76*mm],repeatRows=1,hAlign="LEFT")
    tab.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),FOREST),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,MINT]),
        ("LINEBELOW",(0,0),(-1,-1),0.2,colors.HexColor("#CBDCD1")),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("TOPPADDING",(0,0),(-1,-1),5),
        ("BOTTOMPADDING",(0,0),(-1,-1),5),
    ]))
    # Header is a paragraph to avoid invisible white text in Paragraph style.
    tab._cellvalues[0] = [P("<font color='white'><b>Tema</b></font>","table"),
                          P("<font color='white'><b>Situação</b></font>","table")]
    story.extend([tab, Spacer(1,8*mm),
        P("SOBREPOSIÇÕES — EVIDÊNCIAS DISPONÍVEIS", "h2"),
        P(f'Bases efetivamente analisadas: <b>{ev["analyzed_count"]}</b>. '
          f'Bases sem confirmação: <b>{ev["inconclusive_count"]}</b>. '
          f'Fontes analisadas com incidência: <b>{ev["sources_with_intersections"]}</b>.'),
    ])
    if ev["analyzed_count"] == 0:
        story.append(P("<b>INCONCLUSIVO:</b> nenhuma base territorial foi efetivamente "
                       "analisada neste registro. Não é possível afirmar ausência de sobreposições."))
    source_rows = [[P("<font color='white'><b>Fonte / órgão</b></font>","table"),
                    P("<font color='white'><b>Estado</b></font>","table"),
                    P("<font color='white'><b>Feições</b></font>","table")]]
    for item in ev["sources"]:
        done = item["status"] == "ANALYZED"
        count = str(item["matched_features"]) if done else "—"
        situation = "Analisada" if done else ("Falha" if item["status"] == "FAILED" else "Indisponível")
        source_rows.append([P(_safe(item["name"])+"<br/>"+_safe(item["institution"]),"table"),
                            P(situation,"table"), P(count,"table")])
    if len(source_rows) > 1:
        table2=Table(source_rows,colWidths=[110*mm,40*mm,22*mm],repeatRows=1,hAlign="LEFT")
        table2.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),FOREST),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,MINT]),
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("LINEBELOW",(0,0),(-1,-1),0.2,colors.HexColor("#CBDCD1")),
            ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
        ]))
        story.append(table2)
    monitoring = snapshot.get("monitoring_result")
    if monitoring:
        story.append(P("MONITORAMENTO AMBIENTAL — INPE", "h2"))
        if monitoring.get("status") == "ANALYZED":
            story.extend([
                P("Produto: <b>" + _safe(monitoring.get("layer_title") or monitoring.get("layer")) + "</b>"),
                P(f'Feições incidentes: <b>{int(monitoring["count"])}</b>; '
                  f'área espacial única: <b>{float(monitoring.get("overlap_hectares") or 0):,.4f} ha</b>.'),
                P("Fonte: " + _safe(monitoring.get("source")) +
                  " | Consulta: " + _safe(monitoring.get("queried_at")), "small"),
            ])
            for item in monitoring.get("features", [])[:60]:
                story.append(P("Feição: " + _safe(item.get("id")) +
                               " | Interseção: " + _safe(item.get("overlap_hectares")) +
                               " ha", "small"))
            story.append(P(_safe(monitoring.get("warning")), "small"))
        else:
            story.append(P("Consulta não concluída; a ausência de ocorrências "
                           "não foi comprovada para a camada selecionada."))
    embargo = snapshot.get("ibama_embargos")
    if embargo and embargo.get("status") != "UNAVAILABLE":
        story.extend([
            P("FISCALIZAÇÃO AMBIENTAL — EMBARGOS IBAMA", "h2"),
            P(f'Feições incidentes: <b>{int(embargo["count"])}</b>. '
              f'Área espacial única sobreposta: '
              f'<b>{float(embargo.get("overlap_hectares") or 0):,.4f} ha</b>.'),
            P("Fonte: " + _safe(embargo.get("source")) +
              " | Consulta: " + _safe(embargo.get("queried_at")), "small"),
        ])
        for row in embargo.get("features", [])[:60]:
            story.append(P(
                "Termo: <b>" + _safe(row.get("term") or "Não informado") +
                "</b> | Processo: " + _safe(row.get("process") or "Não informado") +
                " | Área de interseção: " +
                _safe(row.get("overlap_hectares")) + " ha", "small",
            ))
        story.append(P(_safe(embargo.get("warning")), "small"))
    else:
        story.extend([
            P("FISCALIZAÇÃO AMBIENTAL — EMBARGOS IBAMA", "h2"),
            P("Dados não disponíveis para conclusão nesta execução. A falta "
              "de resposta não representa ausência de embargos."),
        ])
    story.extend([
        KeepTogether([
            P("METODOLOGIA E LIMITAÇÕES", "h2"),
            P("As informações acima são snapshots de análises territoriais já "
              "registradas. Bases não executadas não foram contabilizadas como "
              "sem ocorrências. Cada fonte pode apresentar defasagem temporal. "
              "A delimitação cadastral não constitui prova de domínio ou "
              "regularidade ambiental; estudos técnicos e consultas oficiais "
              "continuam necessários."),
            P("Esta prévia não é um laudo, não possui verificação pública de "
              "assinatura e não inclui certificação ou QR de autenticidade.", "small"),
        ]),
    ])
    doc.build(story, onFirstPage=_page_frame, onLaterPages=_page_frame)
    return buf.getvalue()


def run_consolidated_job(job_id: UUID) -> None:
    """FastAPI BackgroundTask; persisted across process completion, not queue-durable.

    A future dedicated worker must pick up orphaned jobs after API restart.
    """
    with SessionLocal() as db:
        job = db.get(RuralConsolidatedJob, job_id)
        if not job or job.status != "QUEUED":
            return
        try:
            job.status = "PROCESSING"
            job.progress_percent = 15
            db.commit()
            analysis = db.get(Analysis, job.source_analysis_id)
            if analysis is None:
                raise ValueError("Análise de origem indisponível.")
            snap = build_job_snapshot(db, analysis)
            # Freeze the same geometry used for the existing territorial analysis.
            geometry_json = db.scalar(
                text("SELECT ST_AsGeoJSON(input_geom, 9) FROM analyses WHERE id=:id"),
                {"id": analysis.id},
            )
            if not geometry_json:
                raise ValueError("Perímetro ausente para fiscalização.")
            # Never share mutable nested lists/dicts with SQLAlchemy JSON state.
            # The in-place provider updates below must be detected and persisted.
            job.snapshot_json = deepcopy(snap)
            job.progress_percent = 35
            db.commit()
            geom = json.loads(geometry_json)
            analyze_ibama_embargos(snap, geom)
            job.snapshot_json = deepcopy(snap)
            job.progress_percent = 60
            db.commit()
            analyze_monitoring(
                snap, geom, (job.options_json or {}).get("monitoring_layer_name")
            )
            job.snapshot_json = deepcopy(snap)
            job.progress_percent = 80
            db.commit()
            data = render_preliminary_consolidated_pdf(snap)
            if not data.startswith(b"%PDF") or len(data) > 12*1024*1024:
                raise ValueError("PDF consolidado inválido ou excessivamente grande.")
            pathroot = Path(get_settings().storage_dir).resolve() / "rural-consolidated"
            pathroot.mkdir(parents=True,exist_ok=True)
            final = pathroot / (str(job.id) + ".pdf")
            tmp = pathroot / (str(job.id) + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(final)
            job.pdf_relative_path = str(job.id) + ".pdf"
            job.pdf_sha256 = sha256(data).hexdigest()
            job.status = "COMPLETED"
            job.progress_percent = 100
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
        except Exception as exc:
            db.rollback()
            job = db.get(RuralConsolidatedJob, job_id)
            if job:
                job.status = "FAILED"
                job.error_message = (type(exc).__name__ + ": " + str(exc))[:300]
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
