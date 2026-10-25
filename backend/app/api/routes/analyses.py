from fastapi import APIRouter,BackgroundTasks,Depends,HTTPException,Response
from fastapi.responses import HTMLResponse
from html import escape
from uuid import UUID
from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.analysis import AnalysisAccepted,AnalysisRequest,AnalysisResponse
from app.services.analyzer import prepare_analysis,run_analysis_background
from app.services.sigef_ods import build_sigef_simulation_ods
from app.services.auth import require_permission
from app.models.analysis import Analysis,AnalysisResult
from app.models.auth import User
from app.models.catalog import GeoFeature,Source,SourceVersion
router=APIRouter(prefix="/analyses",tags=["Análises"],dependencies=[Depends(require_permission("analysis.view"))])
@router.post("",response_model=AnalysisAccepted,status_code=202,dependencies=[Depends(require_permission("analysis.execute"))])
def create_analysis(
    payload: AnalysisRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("analysis.execute")),
):
    try:
        analysis = prepare_analysis(
            db,
            payload.name,
            payload.geometry,
            created_by_user_id=current_user.id,
        )
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc
    analysis.subject_json = dict(payload.subject or {})
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    background_tasks.add_task(run_analysis_background,analysis.id,payload.name,payload.geometry,payload.source_ids,payload.incra_uf)
    return {"analysis_id":analysis.id,"name":analysis.name,"geometry_kind":analysis.geometry_kind,"area_hectares":round(analysis.area_hectares,4) if analysis.area_hectares is not None else None,"status":"QUEUED"}

@router.get("")
def list_analyses(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("analysis.view")),
):
    query = (
        select(Analysis, User)
        .outerjoin(User, User.id == Analysis.created_by_user_id)
        .order_by(Analysis.created_at.desc())
        .limit(500)
    )

    user_roles = {role.code for role in current_user.roles}

    if "ADMINISTRADOR" not in user_roles:
        query = query.where(
            Analysis.created_by_user_id == current_user.id
        )

    rows = db.execute(query).all()

    return [
        {
            "id": str(analysis.id),
            "name": analysis.name,
            "geometry_kind": analysis.geometry_kind,
            "area_hectares": (
                round(analysis.area_hectares, 4)
                if analysis.area_hectares is not None
                else None
            ),
            "status": analysis.status,
            "created_at": (
                analysis.created_at.isoformat()
                if analysis.created_at
                else None
            ),
            "updated_at": (
                analysis.updated_at.isoformat()
                if analysis.updated_at
                else None
            ),
            "created_by": (
                {
                    "id": str(user.id),
                    "full_name": user.full_name,
                    "email": user.email,
                }
                if user
                else None
            ),
            "warnings_count": len(analysis.warnings_json or []),
            "error_message": analysis.error_message,
            "subject": analysis.subject_json or {},
        }
        for analysis, user in rows
    ]


def _get_authorized_analysis(
    db: Session,
    analysis_id: UUID,
    current_user: User,
) -> Analysis:
    analysis = db.get(Analysis, analysis_id)

    if not analysis:
        raise HTTPException(404, "Análise não encontrada.")

    roles = {role.code for role in current_user.roles}

    if (
        "ADMINISTRADOR" not in roles
        and analysis.created_by_user_id != current_user.id
    ):
        raise HTTPException(404, "Análise não encontrada.")

    return analysis


@router.get("/{analysis_id}",response_model=AnalysisResponse)
def analysis_status(
    analysis_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("analysis.view")),
):
    analysis = _get_authorized_analysis(
        db,
        analysis_id,
        current_user,
    )
    rows=db.execute(select(AnalysisResult,Source,SourceVersion).join(Source,Source.id==AnalysisResult.source_id).join(SourceVersion,SourceVersion.id==AnalysisResult.source_version_id).where(AnalysisResult.analysis_id==analysis_id).order_by(AnalysisResult.intersects.desc(),Source.institution,Source.name)).all()
    results=[]
    for result,source,version in rows:
        results.append({"source_id":source.id,"source_name":source.name,"institution":source.institution,"reference_date":version.reference_date.isoformat() if version.reference_date else None,"intersects":result.intersects,"matched_features":result.matched_features,"overlap_hectares":result.overlap_hectares,"overlap_percent":result.overlap_percent,"nearest_distance_meters":result.nearest_distance_meters,"access_mode":(result.details or {}).get("access_mode","LOCAL_VECTOR")})
    return {
        "analysis_id": analysis.id,
        "name": analysis.name,
        "geometry_kind": analysis.geometry_kind,
        "area_hectares": (
            round(analysis.area_hectares, 4)
            if analysis.area_hectares is not None
            else None
        ),
        "results": results,
        "warnings": analysis.warnings_json or [],
        "source_statuses": analysis.source_status_json or [],
        "status": analysis.status,
        "error_message": analysis.error_message,
        "subject": analysis.subject_json or {},
    }

@router.get(
    "/{analysis_id}/sigef-ods",
    dependencies=[Depends(require_permission("analysis.export"))],
)
def analysis_sigef_ods(
    analysis_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("analysis.export")),
):
    analysis = _get_authorized_analysis(
        db,
        analysis_id,
        current_user,
    )

    try:
        data = build_sigef_simulation_ods(
            db,
            analysis,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    filename = (
        f"SIMULACAO_SIGEF_{str(analysis.id)[:8]}.ods"
    )

    return Response(
        content=data,
        media_type=(
            "application/"
            "vnd.oasis.opendocument.spreadsheet"
        ),
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
            ),
            "Cache-Control": "no-store",
        },
    )


@router.get("/{analysis_id}/report",response_class=HTMLResponse,dependencies=[Depends(require_permission("analysis.export"))])
def analysis_report(
    analysis_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("analysis.export")),
):
    analysis = _get_authorized_analysis(
        db,
        analysis_id,
        current_user,
    )
    if analysis.status!="COMPLETED": raise HTTPException(409,"A análise ainda não foi concluída.")
    rows=db.execute(select(AnalysisResult,Source,SourceVersion).join(Source,Source.id==AnalysisResult.source_id).join(SourceVersion,SourceVersion.id==AnalysisResult.source_version_id).where(AnalysisResult.analysis_id==analysis_id).order_by(AnalysisResult.intersects.desc(),Source.institution,Source.name)).all()
    body=[]
    detail_sections=[]
    for result,source,version in rows:
        situation="INTERFERE" if result.intersects else "SEM INTERFERÊNCIA"
        body.append(f"<tr><td><strong>{escape(source.name)}</strong><small>{escape(source.institution)}</small></td><td>{situation}</td><td>{result.matched_features}</td><td>{result.overlap_hectares:,.4f}</td><td>{result.overlap_percent:,.2f}%</td><td>{escape(version.reference_date.isoformat() if version.reference_date else 'não informada')}</td></tr>")
        if result.intersects:
            matched=db.execute(
                select(GeoFeature.external_id,GeoFeature.name,GeoFeature.properties)
                .where(GeoFeature.version_id==version.id,func.ST_Intersects(GeoFeature.geom,analysis.input_geom))
                .limit(40)
            ).all()
            items=[]
            preferred=("PROCESSO","FASE","NOME","SUBS","USO","AREA_HA","UF","ULT_EVENTO","DSProcesso","cod_imovel","status","nome")
            for external_id,feature_name,properties in matched:
                attributes=dict(properties or {})
                pairs=[]
                for key in preferred:
                    value=attributes.get(key)
                    if value not in (None,""):
                        pairs.append(f"<dt>{escape(key.replace('_',' ').title())}</dt><dd>{escape(str(value))}</dd>")
                label=feature_name or attributes.get("PROCESSO") or external_id or "Feição sem nome"
                items.append(f"<article class='feature'><h4>{escape(str(label))}</h4><dl>{''.join(pairs) or f'<dt>Identificador</dt><dd>{escape(str(external_id or "—"))}</dd>'}</dl></article>")
            suffix=f"<p class='note'>Exibindo 40 de {result.matched_features} feições.</p>" if result.matched_features>40 else ""
            detail_sections.append(f"<section class='details'><h3>{escape(source.institution)} · {escape(source.name)}</h3><div class='feature-grid'>{''.join(items)}</div>{suffix}</section>")
    area="Ponto" if analysis.area_hectares is None else f"{analysis.area_hectares:,.4f} ha"
    generated=analysis.created_at.strftime("%d/%m/%Y %H:%M") if analysis.created_at else ""
    warnings="".join(f"<li>{escape(str(item))}</li>" for item in (analysis.warnings_json or []))
    return HTMLResponse(f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><title>Relatório territorial - {escape(analysis.name)}</title><style>@page{{size:A4;margin:16mm}}body{{font:13px Arial;color:#18352a;margin:0}}header{{border-bottom:4px solid #0d6847;padding-bottom:14px;margin-bottom:22px}}h1{{margin:4px 0;font-size:25px}}h2{{font-size:15px;margin:22px 0 8px}}h3{{font-size:14px;border-bottom:2px solid #0d6847;padding-bottom:5px}}h4{{margin:0 0 7px}}.eyebrow,small,.note{{display:block;color:#688078;font-size:10px;text-transform:uppercase;letter-spacing:.08em}}.summary{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}.summary div,.feature{{border:1px solid #cddbd5;border-radius:8px;padding:12px}}.summary strong{{display:block;font-size:18px;margin-top:4px}}table{{width:100%;border-collapse:collapse}}th,td{{border-bottom:1px solid #dce6e1;padding:9px 6px;text-align:left;vertical-align:top}}th{{background:#edf5f1;font-size:10px;text-transform:uppercase}}.method,.warnings{{margin-top:18px;padding:12px;background:#edf5f1;border-left:4px solid #0d6847}}.warnings{{background:#fff4e5;border-color:#d88b18}}.feature-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}}dl{{display:grid;grid-template-columns:100px 1fr;gap:3px 7px;margin:0}}dt{{font-size:10px;color:#688078;text-transform:uppercase}}dd{{margin:0;overflow-wrap:anywhere}}.details{{break-inside:avoid;margin-top:20px}}footer{{margin-top:24px;padding-top:12px;border-top:1px solid #ccd9d3;color:#688078}}.actions{{position:fixed;right:18px;top:18px}}button{{background:#0d6847;color:white;border:0;border-radius:7px;padding:10px 14px;font-weight:bold}}@media print{{.actions{{display:none}}.feature-grid{{grid-template-columns:repeat(2,1fr)}}}}</style></head><body><div class='actions'><button onclick='window.print()'>Salvar / imprimir PDF</button></div><header><span class='eyebrow'>AMAZÔNIKA GEOESPACIAL · RELATÓRIO TÉCNICO</span><h1>{escape(analysis.name)}</h1><small>Gerado em {generated} · SIRGAS 2000 (EPSG:4674)</small></header><section class='summary'><div>Geometria<strong>{escape(analysis.geometry_kind)}</strong></div><div>Área analisada<strong>{area}</strong></div><div>Fontes vetoriais<strong>{len(rows)}</strong></div></section><div class='method'><strong>Metodologia vetorial</strong><br>As identificações e os cálculos foram executados no PostGIS com os vetores das versões relacionadas abaixo. Serviços WMS foram usados somente como referência visual e não participaram do cálculo.</div><h2>Resultado das sobreposições</h2><table><thead><tr><th>Fonte oficial</th><th>Resultado</th><th>Feições</th><th>Área (ha)</th><th>Percentual</th><th>Referência</th></tr></thead><tbody>{''.join(body) or '<tr><td colspan=6>Nenhuma base vetorial disponível.</td></tr>'}</tbody></table>{f"<div class='warnings'><strong>Fontes não concluídas</strong><ul>{warnings}</ul></div>" if warnings else ''}<h2>Feições identificadas</h2>{''.join(detail_sections) or '<p>Nenhuma feição sobreposta.</p>'}<footer>Documento gerado automaticamente. A ausência de sobreposição indica o resultado das bases e versões listadas na data da consulta e não substitui certidões dos órgãos competentes.</footer></body></html>""")
