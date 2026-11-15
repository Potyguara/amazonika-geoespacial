"""GEO-97: conferência espacial de parcelas contra versões vetoriais SIGEF locais.

Apenas as versões READY/current das fontes oficiais carregadas no PostGIS podem
ser verificadas; WMS/GeoNode remoto sem geometrias vetoriais não constitui
resultado negativo. A API não desloca vértices nem emite liberação SIGEF.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from shapely.geometry import shape
from shapely.validation import explain_validity

from app.db.session import get_db
from app.models.catalog import Source, SourceVersion
from app.services.auth import require_permission

router = APIRouter(
    prefix="/technical-pieces/official-overlaps",
    tags=["Sobreposição de parcelas oficiais — conferência GEO97"],
    dependencies=[Depends(require_permission("analysis.execute"))],
)

class CandidateVertex(BaseModel):
    name: str = Field(min_length=3, max_length=40)
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)

class OverlapRequest(BaseModel):
    geometry: dict[str, Any]
    include_touching: bool = True
    near_m: float = Field(default=3, ge=0, le=30)
    max_adjust_m: float = Field(default=0.5, ge=0, le=9)
    ps4_vertices: list[CandidateVertex] = Field(default_factory=list, max_length=100)

def _valid_polygon(geojson: dict):
    if geojson.get("type") not in ("Polygon", "MultiPolygon"):
        raise HTTPException(422, "Envie a poligonal GeoJSON (Polygon ou MultiPolygon).")
    try:
        g = shape(geojson)
    except Exception as exc:
        raise HTTPException(422, "GeoJSON inválido.") from exc
    if g.is_empty or not g.is_valid or g.area <= 0:
        raise HTTPException(422, "Poligonal inválida: " + explain_validity(g)[:150])
    if g.geom_type not in ("Polygon", "MultiPolygon") or len(str(geojson)) > 150_000:
        raise HTTPException(422, "Geometria não suportada ou muito extensa.")
    west, south, east, north = g.bounds
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise HTTPException(422, "Coordenadas fora dos limites geográficos.")
    if east-west > 1 or north-south > 1:
        raise HTTPException(422, "A análise é restrita a imóveis com extensão inferior a 1 grau por eixo.")
    return g

@router.post("/check")
def check_official_overlaps(payload: OverlapRequest, db: Session = Depends(get_db)):
    from shapely.geometry import mapping
    from json import dumps
    poly = _valid_polygon(payload.geometry)
    polygon_json = dumps(mapping(poly), separators=(",", ":"))
    sources = db.scalars(select(Source).where(
        Source.is_active.is_(True),
        Source.is_official.is_(True),
        Source.slug.ilike("%sigef%"),
    )).all()

    # Diferenciar a coleção mensal (atualização periódica) da abrangência Brasil.
    status = {
        "SIGEF Mensais": {"checked": False, "status": "SEM_VERSAO_VETORIAL_READY"},
        "SIGEF Brasil": {"checked": False, "status": "SEM_VERSAO_VETORIAL_READY"},
    }
    matches = []
    suggestions = []
    for source in sources:
        token = (source.slug + " " + source.name).lower()
        kind = ("SIGEF Mensais" if "mens" in token else
                "SIGEF Brasil" if "brasil" in token else None)
        if kind is None:
            continue
        # Fonte Brasil antiga foi explicitamente desativada pela pesquisa oficial;
        # jamais ressuscitar essa versão local como conferência negativa confiável.
        if source.slug == "incra-sigef-brasil":
            status[kind] = {
                "checked": False, "status": "GEONODE_REMOTO_SEM_VETOR_ATUAL",
                "source": source.name, "slug": source.slug,
            }
            continue
        # GeoNode WMS não é uma versão vetorial consultável.
        version = db.scalar(select(SourceVersion).where(
            SourceVersion.source_id == source.id,
            SourceVersion.status == "READY",
            SourceVersion.is_current.is_(True),
        ).order_by(SourceVersion.imported_at.desc()).limit(1))
        if not version:
            status[kind] = {
                "checked": False, "status": "SEM_VERSAO_VETORIAL_READY",
                "source": source.name,
                "slug": source.slug,
            }
            continue
        rows = db.execute(text("""
            WITH target AS (
                SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4674) AS geom
            )
            SELECT f.external_id, f.name,
                   ST_AsGeoJSON(ST_Envelope(f.geom)) AS bbox_geojson,
                   ST_Intersects(f.geom, target.geom) AS intersects,
                   ST_Area(ST_CollectionExtract(
                       ST_Intersection(f.geom, target.geom), 3)::geography) AS overlap_m2,
                   ST_Distance(f.geom::geography, target.geom::geography) AS distance_m
              FROM geo_features f
              CROSS JOIN target
             WHERE f.version_id = :version_id
               AND f.geom && ST_Expand(target.geom, :near_deg)
               AND ST_DWithin(f.geom::geography, target.geom::geography, :near_m)
             ORDER BY ST_Intersects(f.geom, target.geom) DESC,
                      ST_Distance(f.geom::geography, target.geom::geography)
             LIMIT 101
        """), {
            "geom": polygon_json,
            "version_id": version.id,
            "near_m": payload.near_m,
            "near_deg": (payload.near_m + 1) / 100000,
        }).mappings().all()
        truncated = len(rows) > 100
        for row in rows[:100]:
            overlap = max(float(row["overlap_m2"] or 0), 0)
            relation = ("SOBREPOSICAO" if overlap > 0.01 else
                        "TOQUE" if row["intersects"] else "PROXIMIDADE")
            if relation == "TOQUE" and not payload.include_touching:
                continue
            matches.append({
                "source": kind, "name": row["name"],
                "external_id": row["external_id"],
                "relation": relation, "overlap_m2": round(overlap, 2),
                "distance_m": round(float(row["distance_m"] or 0), 3),
                "bbox_geojson": row["bbox_geojson"],
                "adjustment": "SUGESTAO_SOMENTE_REVISAO_RT",
            })
        # Sugestões geométricas de encaixe, sem escrita em banco. Executadas
        # apenas se uma versão oficial vetorial estiver efetivamente disponível.
        if payload.max_adjust_m > 0:
            for vertex in payload.ps4_vertices:
                proposed = db.execute(text("""
                    WITH pt AS (
                      SELECT ST_SetSRID(ST_MakePoint(:lon,:lat),4674) AS geom
                    )
                    SELECT f.external_id, f.name,
                           ST_X(ST_ClosestPoint(ST_Boundary(f.geom),pt.geom)) AS proposed_lon,
                           ST_Y(ST_ClosestPoint(ST_Boundary(f.geom),pt.geom)) AS proposed_lat,
                           ST_Distance(ST_Boundary(f.geom)::geography,
                                       pt.geom::geography) AS displacement_m
                    FROM geo_features f CROSS JOIN pt
                    WHERE f.version_id=:version_id
                      AND f.geom && ST_Expand(pt.geom,:near_deg)
                      AND ST_DWithin(ST_Boundary(f.geom)::geography,
                                     pt.geom::geography,:max_shift)
                    ORDER BY displacement_m ASC LIMIT 1
                """), {
                    "lon": vertex.longitude, "lat": vertex.latitude,
                    "version_id": version.id,
                    "near_deg": payload.max_adjust_m / 100000 + 1e-6,
                    "max_shift": payload.max_adjust_m,
                }).mappings().first()
                if proposed:
                    delta = float(proposed["displacement_m"])
                    suggestions.append({
                        "vertex": vertex.name,
                        "source": kind, "neighbor_id": proposed["external_id"],
                        "neighbor_name": proposed["name"],
                        "old_lon": vertex.longitude,
                        "old_lat": vertex.latitude,
                        "proposed_lon": float(proposed["proposed_lon"]),
                        "proposed_lat": float(proposed["proposed_lat"]),
                        "displacement_m": round(delta, 3),
                        "classification": "ATE_0_50_M_REVISAO_RT"
                          if delta <= 0.5 else "ACIMA_0_50_M_EXIGE_ANALISE",
                        "applied": False,
                    })
        status[kind] = {
            "checked": True,
            "status": "TRUNCADO" if truncated else "CONSULTADO",
            "source": source.name,
            "slug": source.slug,
            "reference_date": str(version.reference_date) if version.reference_date else None,
            "imported_at": version.imported_at.isoformat() if version.imported_at else None,
            "feature_count": version.feature_count,
        }
    overlap_found = any(m["relation"] == "SOBREPOSICAO" for m in matches)
    complete = all(x["checked"] and x["status"] == "CONSULTADO" for x in status.values())
    return {
        "status": "SOBREPOSICAO_DETECTADA" if overlap_found else
                  ("SEM_INTERSECAO_NAS_BASES_CONSULTADAS" if complete
                   else "VERIFICACAO_INCOMPLETA"),
        "complete": complete,
        "sources": status,
        "matches": matches,
        "suggestions": suggestions,
        "count": len(matches),
        "auto_adjustment_applied": False,
        "note": "Conferência local por versão de base, não substitui consulta e validação SIGEF oficial. "
                "Nenhuma coordenada foi movida. Tolerância de discrepância não é permissão para deslocamento automático.",
    }
