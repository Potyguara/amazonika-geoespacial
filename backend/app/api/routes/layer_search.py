"""Search layer attributes and return bounded vector geometry for map focus.

Search is read-only and scoped to a specific source/current READY version.
WMS imagery is not mistaken for a searchable vector dataset. CAR has a
separate exact-code official SICAR WFS adapter, with clear errors.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.catalog import Source, SourceVersion
from app.services.auth import require_permission
from app.services.rural_official_car import (
    OfficialCarQueryError, normalize_car, fetch_car_candidate, resolve_car_candidate,
)

router = APIRouter(
    prefix="/layer-search",
    tags=["Pesquisa por atributos de camadas"],
    dependencies=[Depends(require_permission("sources.view"))],
)

# Best-effort keys of common public official vector datasets; source-specific
# keys can also be selected after discovery in /fields.
PREFERRED_FIELDS = (
    "cod_imovel", "codigo_imovel", "cod_car", "numero_car",
    "num_processo", "numero_processo", "processo", "nr_processo",
    "numero", "num_tad", "codigo", "nome", "denominacao",
    "external_id",
)
FIELD_RE = re.compile(r"^[\w.-]{1,80}$", re.UNICODE)
MAX_RESULTS = 15


def _current_version(db: Session, source_id: UUID):
    source = db.get(Source, source_id)
    if not source or not source.is_active:
        raise HTTPException(404, "Camada não encontrada ou inativa.")
    version = db.scalar(
        select(SourceVersion).where(
            SourceVersion.source_id == source.id,
            SourceVersion.is_current.is_(True),
            SourceVersion.status == "READY",
        ).order_by(SourceVersion.imported_at.desc()).limit(1),
    )
    if not version:
        raise HTTPException(
            409, "Camada sem versão vetorial local pesquisável. "
            "Uma exibição WMS não fornece atributos para busca; "
            "configure uma fonte vetorial WFS/GeoPackage correspondente.",
        )
    return source, version


def _fields(db: Session, version_id: UUID) -> list[str]:
    rows = db.execute(text("""
        SELECT properties FROM geo_features
        WHERE version_id = :version_id
        LIMIT 50
    """), {"version_id": version_id}).all()
    discovered: set[str] = {"external_id", "name"}
    for (properties,) in rows:
        if not isinstance(properties, dict):
            continue
        for key, value in properties.items():
            if (
                isinstance(key, str) and FIELD_RE.fullmatch(key)
                and isinstance(value, (str, int, float))
                and not isinstance(value, bool)
                and not any(s in key.lower() for s in (
                    "cpf", "cnpj", "email", "telefone", "celular", "password",
                    "senha", "token", "chave", "proprietario", "titular",
                    "responsavel", "endereco", "pessoa",
                ))
            ):
                discovered.add(key)
    return sorted(discovered, key=lambda key: (
        key.lower() not in PREFERRED_FIELDS,
        key.lower(),
    ))[:100]


@router.get("/fields")
def layer_fields(
    source_id: UUID,
    db: Session = Depends(get_db),
):
    source, version = _current_version(db, source_id)
    fields = _fields(db, version.id)
    return {
        "source_id": str(source.id),
        "source_name": source.name,
        "version_id": str(version.id),
        "fields": fields,
        "default_field": "cod_imovel" if "cod_imovel" in fields else (
            next((v for v in fields if v.lower() in PREFERRED_FIELDS), "external_id")
        ),
        "reference_date": version.reference_date.isoformat() if version.reference_date else None,
    }


def _search_local(
    db: Session, version_id: UUID, field: str, query: str, limit: int,
) -> list[dict]:
    # A bound field name never gets interpolated into SQL, including JSONB key.
    # Prefix search is intentionally bounded to one imported source/version.
    if field not in {"external_id", "name"} and not FIELD_RE.fullmatch(field):
        raise HTTPException(422, "Campo de atributo inválido.")
    pattern = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    sql = text("""
        SELECT id, external_id, name,
          properties,
          ST_AsGeoJSON(
            CASE WHEN ST_NPoints(geom)>10000
              THEN ST_SimplifyPreserveTopology(geom, 0.00001)
              ELSE geom END, 6
          ) AS geometry_json,
          ST_XMin(Box2D(geom)) AS xmin,
          ST_YMin(Box2D(geom)) AS ymin,
          ST_XMax(Box2D(geom)) AS xmax,
          ST_YMax(Box2D(geom)) AS ymax
        FROM geo_features
        WHERE version_id = :version_id
          AND (
            CASE WHEN :field='external_id' THEN external_id
                 WHEN :field='name' THEN name
                 ELSE CAST(properties AS jsonb) ->> :field END
          ) ILIKE :pattern ESCAPE '\\'
        ORDER BY
          CASE WHEN (
            CASE WHEN :field='external_id' THEN external_id
                 WHEN :field='name' THEN name
                 ELSE CAST(properties AS jsonb) ->> :field END
          ) = :query THEN 0 ELSE 1 END, external_id
        LIMIT :limit
    """)
    with db.begin_nested():
        db.execute(text("SET LOCAL statement_timeout='6000ms'"))
        rows = db.execute(sql, {
            "version_id": version_id,
            "field": field, "pattern": pattern, "query": query, "limit": limit,
        }).mappings().all()
    results = []
    for row in rows:
        raw_geom = row["geometry_json"]
        if not isinstance(raw_geom, str) or len(raw_geom) > 600_000:
            raise HTTPException(413, "Feição localizada, mas sua geometria excede o limite de visualização.")
        bbox = [row[k] for k in ("xmin", "ymin", "xmax", "ymax")]
        if any(value is None for value in bbox):
            continue
        props = row["properties"] if isinstance(row["properties"], dict) else {}
        safe_props = {
            k: v for k, v in list(props.items())[:100]
            if isinstance(v, (str, int, float, bool))
            and not any(term in k.lower() for term in (
                "cpf", "cnpj", "email", "telefone", "celular",
                "senha", "password", "token", "endereco",
                "proprietario", "titular", "responsavel",
            ))
        }
        results.append({
            "feature_id": str(row["id"]),
            "title": str(row["name"] or row["external_id"] or "Feição localizada")[:180],
            "external_id": row["external_id"],
            "matched_field": field,
            "matched_value": str(
                row["external_id"] if field == "external_id" else
                row["name"] if field == "name" else props.get(field) or ""
            )[:160],
            "properties": safe_props,
            "bbox": [float(x) for x in bbox],
            "geometry": json.loads(raw_geom),
        })
    return results


@router.get("/features")
def search_features(
    source_id: UUID,
    q: str = Query(min_length=2, max_length=120),
    field: str = Query(default="external_id", max_length=80),
    limit: int = Query(default=10, ge=1, le=MAX_RESULTS),
    db: Session = Depends(get_db),
):
    term = q.strip()
    if len(term) < 2:
        raise HTTPException(422, "Informe pelo menos dois caracteres.")
    source, version = _current_version(db, source_id)
    fields = _fields(db, version.id)
    if field not in fields:
        raise HTTPException(422, "Campo não disponível na versão vetorial desta camada.")
    try:
        found = _search_local(db, version.id, field, term, limit)
    except SQLAlchemyError as exc:
        raise HTTPException(503, "Busca temporariamente indisponível ou excedeu o tempo seguro.") from exc
    return {
        "source_id": str(source.id), "source_name": source.name,
        "version_id": str(version.id),
        "field": field, "query": term,
        "results": found, "limit": limit,
        "truncated": len(found) >= limit,
    }


@router.get("/car")
def find_official_car(
    car_code: str = Query(min_length=20, max_length=100),
):
    try:
        code = normalize_car(car_code)
        candidate = fetch_car_candidate(code)
        if candidate is None:
            return {"source_name": "CAR — SICAR oficial", "results": []}
        resolved = resolve_car_candidate(code, candidate["feature_id"])
        geom = resolved["geometry"]
        if len(json.dumps(geom)) > 600_000:
            raise HTTPException(422, "Geometria CAR muito detalhada para destacar no mapa.")
        from shapely.geometry import shape
        bounds = shape(geom).bounds
        return {
            "source_name": "CAR — SICAR oficial",
            "results": [{
                "feature_id": candidate["feature_id"],
                "title": str(candidate.get("name") or code),
                "external_id": code, "matched_field": "cod_imovel",
                "matched_value": code,
                "properties": {
                    "cod_imovel": code,
                    "area_hectares": candidate.get("area_hectares"),
                    "reference_date": candidate.get("reference_date"),
                    "notice": candidate.get("notice"),
                },
                "bbox": list(bounds), "geometry": geom,
            }],
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(422, str(exc)[:180]) from exc
    except OfficialCarQueryError as exc:
        raise HTTPException(503, "O WFS oficial do SICAR está indisponível ou não concluiu a pesquisa.") from exc


ANM_PROCESS_LAYER = (
    "https://geo.anm.gov.br/arcgis/rest/services/"
    "SIGMINE/dados_anm/MapServer/0/query"
)
ANM_PROCESS_PATTERN = re.compile(r"^(\d{3})\.?(\d{3})/(\d{4})$")


@router.get("/anm-process")
def find_official_anm_process(
    process_number: str = Query(min_length=10, max_length=20),
):
    """Exact public ANM process (active SIGMINE layer 0).

    Uses a fixed approved URL and integer-only SQL predicate. No
    caller-supplied remote URL or arbitrary ArcGIS WHERE clause.
    """
    value = process_number.strip()
    match = ANM_PROCESS_PATTERN.fullmatch(value)
    if not match:
        raise HTTPException(
            422, "Informe o processo ANM no formato 850.123/2020.",
        )
    numero = int(match.group(1) + match.group(2))
    ano = int(match.group(3))
    params = {
        "where": f"NUMERO={numero} AND ANO={ano}",
        "outFields": "PROCESSO,NUMERO,ANO,FASE,SUBS,AREA_HA,UF,DSProcesso",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
        "resultRecordCount": "15",
    }
    url = ANM_PROCESS_LAYER + "?" + urlencode(params)
    try:
        request = Request(url, headers={
            "User-Agent": "Amazonika-Geoespacial/1.0",
            "Accept": "application/geo+json,application/json",
        })
        with urlopen(request, timeout=20) as resp:
            if "json" not in (resp.headers.get("Content-Type") or "").lower():
                raise ValueError("Resposta oficial não é GeoJSON")
            raw = resp.read(2_500_001)
        if len(raw) > 2_500_000:
            raise ValueError("Resposta muito grande")
        payload = json.loads(raw)
        if (
            not isinstance(payload, dict)
            or payload.get("type") != "FeatureCollection"
            or not isinstance(payload.get("features"), list)
            or payload.get("exceededTransferLimit")
            or len(payload["features"]) >= 15
        ):
            raise ValueError("Consulta ANM incompleta ou inválida")
        from shapely.geometry import shape
        results = []
        for record in payload["features"]:
            if not isinstance(record, dict) or not isinstance(record.get("geometry"), dict):
                raise ValueError("Processo ANM sem geometria")
            geometry = record["geometry"]
            if len(json.dumps(geometry)) > 600_000:
                raise ValueError("Geometria excedeu limite para o mapa")
            obj = shape(geometry)
            if obj.is_empty or not obj.is_valid:
                raise ValueError("Geometria ANM inválida")
            props = record.get("properties") or {}
            if not isinstance(props, dict):
                raise ValueError("Atributos ANM inválidos")
            result_number = props.get("NUMERO")
            result_year = props.get("ANO")
            if str(result_number) != str(numero) or str(result_year) != str(ano):
                raise ValueError("Resposta oficial não corresponde ao processo consultado")
            external = str(props.get("PROCESSO") or f"{numero}/{ano}")[:40]
            results.append({
                "feature_id": str(record.get("id") or external)[:100],
                "title": "Processo minerário " + external,
                "external_id": external,
                "matched_field": "PROCESSO",
                "matched_value": external,
                "bbox": list(obj.bounds),
                "geometry": geometry,
                "properties": {
                    field: props.get(field)
                    for field in ("PROCESSO", "NUMERO", "ANO", "FASE",
                                  "SUBS", "AREA_HA", "UF", "DSProcesso")
                    if props.get(field) is not None
                },
            })
        return {
            "source_name": "ANM — SIGMINE oficial (processos ativos)",
            "query": value,
            "results": results,
            "source_url": ANM_PROCESS_LAYER,
        }
    except (HTTPError, URLError, TimeoutError, OSError, ValueError,
            KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            503, "O serviço vetorial da ANM não concluiu a pesquisa. "
                 "Não é possível afirmar ausência do processo.",
        ) from exc
