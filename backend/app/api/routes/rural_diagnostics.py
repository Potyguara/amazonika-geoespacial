"""Rural property discovery by coordinate; no national dataset downloads.

Stage 1 is deliberately read-only: search cadastral geometries already present
in PostGIS. External CAR/WFS integrations can be registered as separate adapters
later, with availability and provenance recorded per source.
"""
from __future__ import annotations

import json
import math
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.catalog import GeoFeature
from app.services.auth import require_permission

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
