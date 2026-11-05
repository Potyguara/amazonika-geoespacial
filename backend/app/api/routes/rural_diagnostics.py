"""Rural property discovery by coordinate; no national dataset downloads.

Stage 1 is deliberately read-only: search cadastral geometries already present
in PostGIS. External CAR/WFS integrations can be registered as separate adapters
later, with availability and provenance recorded per source.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.catalog import GeoFeature
from app.services.auth import require_permission
from app.services.rural_official_sigef import (OfficialSigefQueryError, locate_official_sigef, resolve_official_sigef)
from app.services.rural_official_car import (OfficialCarQueryError, normalize_car, fetch_car_candidate, resolve_car_candidate)
from app.services.rural_monitoring import MonitoringQueryError, monitoring_catalog, monitoring_preview
from app.services.rural_diagnostic_pdf import build_rural_monitoring_pdf
from app.services.rural_ibama_embargos import embargo_preview, IbamaEmbargoError

router = APIRouter(
    prefix="/rural-diagnostics",
    tags=["Diagnóstico Territorial Rural"],
    dependencies=[Depends(require_permission("analysis.view"))],
)

# The candidate query is limited to known cadastral categories. A nearby
# environmental restriction must never be misrepresented as a farm boundary.
CADASTRAL_SLUGS = (
    "incra-sigef%",
    "%snci%",
    "%sicar%",
    "%car-imoveis%",
    "%car-rural%",
    "%assentament%",
)
MAX_CANDIDATES = 20
MAX_GEOMETRY_VERTICES = 120_000


def validate_coordinate(latitude: float, longitude: float) -> tuple[float, float]:
    if (
        not math.isfinite(latitude)
        or not math.isfinite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        raise ValueError("Latitude ou longitude fora do intervalo geográfico.")
    return latitude, longitude


def _source_patterns_sql() -> str:
    return " OR ".join(f"s.slug ILIKE :pattern_{i}" for i in range(len(CADASTRAL_SLUGS)))


def _query_params(latitude: float, longitude: float) -> dict:
    return {
        "latitude": latitude,
        "longitude": longitude,
        **{f"pattern_{i}": pattern for i, pattern in enumerate(CADASTRAL_SLUGS)},
    }


@router.get("/locate")
def locate_rural_property(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    db: Session = Depends(get_db),
):
    """Find *candidate* registered perimeters containing the point.

    A point in several overlapping cadastral records is ambiguous; callers
    must select one explicitly before running an area-based analysis.
    """
    try:
        validate_coordinate(latitude, longitude)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    rows = db.execute(
        text(f"""
            WITH input_point AS (
                SELECT ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4674) AS geom
            )
            SELECT f.id AS feature_id, s.id AS source_id, s.slug AS source_slug,
                   s.name AS source_name, s.institution, f.external_id,
                   f.name AS feature_name, f.properties,
                   v.reference_date, v.imported_at,
                   ST_NPoints(f.geom) AS vertex_count,
                   CASE WHEN ST_Dimension(f.geom) = 2
                        THEN ST_Area(f.geom::geography) / 10000.0
                        ELSE NULL END AS area_hectares
            FROM geo_features f
            JOIN source_versions v ON v.id = f.version_id
            JOIN sources s ON s.id = v.source_id
            CROSS JOIN input_point p
            WHERE v.is_current IS TRUE
              AND v.status = 'READY'
              AND s.is_active IS TRUE
              AND ({_source_patterns_sql()})
              AND ST_Dimension(f.geom) = 2
              AND f.geom && p.geom
              AND ST_Covers(f.geom, p.geom)
            ORDER BY s.name, f.name NULLS LAST, f.external_id NULLS LAST
            LIMIT :limit
        """),
        {**_query_params(latitude, longitude), "limit": MAX_CANDIDATES + 1},
    ).mappings().all()

    has_more = len(rows) > MAX_CANDIDATES
    candidates = []
    for item in rows[:MAX_CANDIDATES]:
        props = item["properties"] if isinstance(item["properties"], dict) else {}
        cadastral_code = next(
            (str(props[key])[:120] for key in
             ("cod_imovel", "cod_car", "car", "parcela_codigo", "codigo_imovel")
             if props.get(key)),
            str(item["external_id"] or "")[:120] or None,
        )
        candidates.append({
            "feature_id": str(item["feature_id"]),
            "source_id": str(item["source_id"]),
            "source_slug": item["source_slug"],
            "source_name": item["source_name"],
            "institution": item["institution"],
            "name": item["feature_name"] or cadastral_code or "Imóvel sem nome cadastral",
            "cadastral_code": cadastral_code,
            "area_hectares": round(float(item["area_hectares"]), 4)
            if item["area_hectares"] is not None else None,
            "vertex_count": item["vertex_count"],
            "reference_date": item["reference_date"].isoformat()
            if item["reference_date"] else None,
            "imported_at": item["imported_at"].isoformat()
            if item["imported_at"] else None,
        })

    return {
        "coordinate": {"latitude": latitude, "longitude": longitude},
        "candidate_count": len(candidates),
        "has_more": has_more,
        "candidates": candidates,
        "coverage": "Apenas perímetros cadastrais com versão ativa no PostGIS.",
        "point_only": len(candidates) == 0,
        "notice": (
            "Selecione e valide o imóvel: coincidência espacial não comprova "
            "propriedade, domínio, regularidade do CAR ou atualização cadastral."
        ),
    }


@router.get("/properties/{feature_id}")
def resolve_rural_perimeter(
    feature_id: UUID,
    db: Session = Depends(get_db),
):
    """Return full selected official/local cadastral geometry when manageable."""
    record = db.execute(
        text(f"""
            SELECT f.id AS feature_id, s.name AS source_name, s.slug AS source_slug,
                   v.reference_date, f.name, f.external_id,
                   ST_NPoints(f.geom) AS vertex_count,
                   ST_AsGeoJSON(f.geom, 8) AS geometry
            FROM geo_features f
            JOIN source_versions v ON v.id = f.version_id
            JOIN sources s ON s.id = v.source_id
            WHERE f.id = :feature_id
              AND v.is_current IS TRUE AND v.status = 'READY'
              AND s.is_active IS TRUE
              AND ({_source_patterns_sql()})
              AND ST_Dimension(f.geom) = 2
              AND ST_NPoints(f.geom) <= :max_vertices
            LIMIT 1
        """),
        {
            "feature_id": feature_id,
            "max_vertices": MAX_GEOMETRY_VERTICES,
            **{f"pattern_{i}": pattern for i, pattern in enumerate(CADASTRAL_SLUGS)},
        },
    ).mappings().first()

    if not record:
        raise HTTPException(
            404,
            "Perímetro não encontrado ou excessivamente detalhado para consulta direta. "
            "Importe o arquivo geoespacial do imóvel para análise.",
        )
    geom = json.loads(record["geometry"])
    if geom.get("type") not in ("Polygon", "MultiPolygon"):
        raise HTTPException(422, "Geometria cadastral incompatível com análise de área.")
    return {
        "feature_id": str(record["feature_id"]),
        "name": record["name"] or record["external_id"] or "Imóvel rural",
        "source_name": record["source_name"],
        "source_slug": record["source_slug"],
        "reference_date": record["reference_date"].isoformat()
        if record["reference_date"] else None,
        "geometry": geom,
        "notice": "Geometria cadastral para triagem; confirme a versão antes de uso técnico.",
    }


class OfficialSigefSelection(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    feature_token: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


@router.get("/official-sigef/locate")
def locate_sigef_official(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
):
    """Find official SIGEF perimeters that *actually cover* the supplied point."""
    try:
        validate_coordinate(latitude, longitude)
        return locate_official_sigef(latitude, longitude)
    except OfficialSigefQueryError as exc:
        raise HTTPException(
            503, "Consulta SIGEF oficial indisponível ou inconclusiva: " + str(exc)[:260]
        ) from exc


@router.post("/official-sigef/perimeter", dependencies=[Depends(require_permission("analysis.execute"))])
def retrieve_official_sigef_perimeter(payload: OfficialSigefSelection):
    """Resolve selected perimeter only after rechecking the official GeoNode data."""
    try:
        validate_coordinate(payload.latitude, payload.longitude)
        return resolve_official_sigef(
            payload.latitude, payload.longitude, payload.feature_token
        )
    except OfficialSigefQueryError as exc:
        raise HTTPException(409, str(exc)[:260]) from exc


class OfficialCarSelection(BaseModel):
    car_code: str = Field(min_length=40, max_length=60)
    feature_token: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


@router.get("/official-car/lookup")
def locate_car_official(car_code: str = Query(..., min_length=40, max_length=60)):
    """Exact lookup in the public CAR layer for the code's UF, not a UF scan."""
    try:
        code = normalize_car(car_code)
        candidate = fetch_car_candidate(code)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except OfficialCarQueryError as exc:
        raise HTTPException(503, str(exc)[:280]) from exc
    return {
        "searched_code": code,
        "candidate_count": 1 if candidate else 0,
        "candidates": [candidate] if candidate else [],
        "status": "FOUND" if candidate else "NOT_FOUND_IN_PUBLIC_WFS",
        "coverage": "Consulta exata ao WFS público SICAR da UF indicada no código.",
        "notice": "Ausência no serviço público não significa inexistência de inscrição CAR.",
    }


@router.post("/official-car/perimeter", dependencies=[Depends(require_permission("analysis.execute"))])
def retrieve_official_car_perimeter(payload: OfficialCarSelection):
    """Revalidate the official CAR geometry before using it for spatial analysis."""
    try:
        return resolve_car_candidate(payload.car_code, payload.feature_token)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except OfficialCarQueryError as exc:
        raise HTTPException(409, str(exc)[:280]) from exc


class MonitoringPreviewRequest(BaseModel):
    layer_name: str = Field(min_length=1, max_length=160)
    geometry: dict


@router.get("/monitoring/layers")
def rural_monitoring_layers():
    """List current public PRODES/DETER WFS layers; never infer layer names."""
    try:
        return monitoring_catalog()
    except MonitoringQueryError as exc:
        raise HTTPException(503, str(exc)[:260]) from exc


@router.post("/monitoring/preview", dependencies=[Depends(require_permission("analysis.execute"))])
def rural_monitoring_preview(payload: MonitoringPreviewRequest):
    """Read-only bounded spatial intersection with a selected official layer."""
    try:
        return monitoring_preview(payload.layer_name, payload.geometry)
    except ValueError as exc:
        raise HTTPException(422, str(exc)[:260]) from exc
    except MonitoringQueryError as exc:
        raise HTTPException(503, str(exc)[:260]) from exc


class RuralPreviewPdfRequest(BaseModel):
    """Reference to a candidate, not a user-submitted geometry or result."""
    retrieval: Literal["LOCAL_VECTOR", "OFFICIAL_WFS", "OFFICIAL_CAR_WFS"]
    feature_id: str = Field(min_length=32, max_length=64)
    layer_name: str | None = Field(default=None, max_length=160)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    car_code: str | None = Field(default=None, max_length=60)


def _resolve_pdf_subject(payload: RuralPreviewPdfRequest, db: Session) -> dict:
    """Re-fetch candidate from its source. Never trust client geometry or totals."""
    if payload.retrieval == "LOCAL_VECTOR":
        try:
            identifier = UUID(payload.feature_id)
        except ValueError as exc:
            raise HTTPException(422, "Identificador da geometria local inválido.") from exc
        return resolve_rural_perimeter(identifier, db)
    if len(payload.feature_id) != 64:
        raise HTTPException(422, "Identificador de feição oficial inválido.")
    if payload.retrieval == "OFFICIAL_WFS":
        if payload.latitude is None or payload.longitude is None:
            raise HTTPException(422, "Coordenada necessária para recuperar parcela SIGEF.")
        try:
            return resolve_official_sigef(
                payload.latitude, payload.longitude, payload.feature_id
            )
        except OfficialSigefQueryError as exc:
            raise HTTPException(409, str(exc)[:260]) from exc
    if not payload.car_code:
        raise HTTPException(422, "Código CAR é obrigatório para recuperar o perímetro.")
    try:
        return resolve_car_candidate(payload.car_code, payload.feature_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except OfficialCarQueryError as exc:
        raise HTTPException(409, str(exc)[:260]) from exc


@router.post("/monitoring/preview-pdf",
             dependencies=[Depends(require_permission("analysis.export"))])
def rural_preliminary_pdf(payload: RuralPreviewPdfRequest, db: Session = Depends(get_db)):
    """Generate in-memory preliminary PDF from freshly verified official data.

    No emissions registry, QR authenticity claims or persistent PDF storage:
    this is an explicitly provisional preview, separate from official reports.
    """
    if not payload.layer_name:
        raise HTTPException(422, "Selecione uma camada PRODES/DETER para a prévia PDF.")
    subject = _resolve_pdf_subject(payload, db)
    try:
        monitoring = monitoring_preview(
            payload.layer_name, subject["geometry"], include_geometry=True,
        )
        document = build_rural_monitoring_pdf(
            property_name=subject.get("name") or "Imóvel rural",
            property_source=subject.get("source_name") or "Base cadastral",
            cadastral_code=payload.car_code or subject.get("feature_id"),
            subject_geometry=subject["geometry"],
            monitoring=monitoring,
            generated_at=datetime.now(timezone.utc),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)[:260]) from exc
    except MonitoringQueryError as exc:
        raise HTTPException(503, str(exc)[:260]) from exc
    return Response(
        content=document,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="AMAZONIKA_DIAGNOSTICO_AMBIENTAL_PREVIA.pdf"',
            "Cache-Control": "no-store",
            "X-Report-Type": "preliminary-rural-monitoring",
        },
    )


class IbamaEmbargoPreviewRequest(BaseModel):
    geometry: dict


@router.post("/ibama/embargos/preview",
             dependencies=[Depends(require_permission("analysis.execute"))])
def rural_ibama_embargo_preview(payload: IbamaEmbargoPreviewRequest):
    """Preview official embargo polygons intersecting the selected perimeter."""
    try:
        return embargo_preview(payload.geometry)
    except ValueError as exc:
        raise HTTPException(422, str(exc)[:260]) from exc
    except IbamaEmbargoError as exc:
        raise HTTPException(503, str(exc)[:260]) from exc


@router.post("/ibama/embargos/preview-pdf",
             dependencies=[Depends(require_permission("analysis.export"))])
def rural_ibama_embargo_pdf(payload: RuralPreviewPdfRequest,
                           db: Session = Depends(get_db)):
    """Server-side revalidation and official IBAMA query before PDF generation."""
    subject = _resolve_pdf_subject(payload, db)
    try:
        embargo = embargo_preview(subject["geometry"], include_geometry=True)
        document = build_rural_monitoring_pdf(
            property_name=subject.get("name") or "Imóvel rural",
            property_source=subject.get("source_name") or "Base cadastral",
            cadastral_code=payload.car_code or subject.get("feature_id"),
            subject_geometry=subject["geometry"],
            monitoring=embargo,
            generated_at=datetime.now(timezone.utc),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)[:260]) from exc
    except IbamaEmbargoError as exc:
        raise HTTPException(503, str(exc)[:260]) from exc
    return Response(
        content=document,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="AMAZONIKA_EMBARGOS_IBAMA_PREVIA.pdf"',
            "Cache-Control": "no-store",
            "X-Report-Type": "preliminary-rural-ibama",
        },
    )
