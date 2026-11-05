"""Bounded, read-only intersection against official IBAMA embargo polygons.

ArcGIS REST source confirmed: IBAMA/CENIMA, geometry EPSG:4674,
01_Publicacoes_Bases/adm_embargos_ibama_a/MapServer/0.

The polygon area intersecting a rural property is NOT the embargo's
declared legal area; both values and their provenance are distinct.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from shapely.geometry import shape
from shapely.ops import unary_union
from shapely.errors import GEOSException

from app.services.rural_monitoring import (
    validate_subject, _feature_area_ha, MonitoringQueryError,
)

IBAMA_LAYER = (
    "https://pamgia.ibama.gov.br/server/rest/services/"
    "01_Publicacoes_Bases/adm_embargos_ibama_a/MapServer/0"
)
MAX_FEATURES = 501
MAX_BYTES = 12 * 1024 * 1024
MAX_MATCHED = 500
PUBLIC_FIELDS = (
    "objectid,num_tad,serie_tad,num_processo,dat_embargo,"
    "dat_ult_alteracao,qtd_area_embargada,tipo_area,municipio,uf,"
    "num_auto_infracao,des_tipo_bioma"
)


class IbamaEmbargoError(Exception):
    """Official service failure or an incomplete result."""


def _request_query(params: dict[str, str | int], *, timeout: int = 40) -> dict:
    url = IBAMA_LAYER + "/query?" + urlencode(params)
    request = Request(
        url,
        headers={"User-Agent": "Amazonika-Geoespacial/1.0",
                 "Accept": "application/json,application/geo+json"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_BYTES + 1)
            content_type = (response.headers.get("Content-Type") or "").lower()
    except (OSError, TimeoutError) as exc:
        raise IbamaEmbargoError("Serviço público de embargos do IBAMA indisponível.") from exc
    if len(raw) > MAX_BYTES:
        raise IbamaEmbargoError("Resposta de embargos excedeu o limite de 12 MB.")
    if "json" not in content_type:
        raise IbamaEmbargoError("IBAMA não retornou JSON.")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        raise IbamaEmbargoError("JSON de embargos inválido.") from exc
    if not isinstance(payload, dict) or payload.get("error"):
        message = str((payload or {}).get("error", {}).get("message", "") if isinstance(payload, dict) else "")[:160]
        raise IbamaEmbargoError("ArcGIS IBAMA recusou a consulta. " + message)
    return payload


def _bbox_filter(subject) -> dict[str, str | int]:
    minx, miny, maxx, maxy = subject.bounds
    return {
        "where": "1=1",
        "geometry": f"{minx:.8f},{miny:.8f},{maxx:.8f},{maxy:.8f}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4674,
        "spatialRel": "esriSpatialRelIntersects",
        "outSR": 4326,
        "f": "geojson",
    }


def embargo_preview(geometry: dict, *, include_geometry: bool = False) -> dict:
    subject = validate_subject(geometry)
    common = _bbox_filter(subject)
    # This count query has no geometry and lets us fail early without
    # transferring a truncated feature collection or inventing 'zero'.
    count_params = {
        **common, "returnCountOnly": "true", "f": "json",
    }
    count_response = _request_query(count_params, timeout=25)
    count = count_response.get("count")
    if not isinstance(count, int) or count < 0:
        raise IbamaEmbargoError("IBAMA não informou quantidade confiável de feições.")
    if count > MAX_MATCHED:
        raise IbamaEmbargoError(
            "Muitas ocorrências na extensão: consulta excedeu 500 polígonos; "
            "requer divisão do imóvel em blocos."
        )
    query_params = {
        **common, "outFields": PUBLIC_FIELDS,
        "returnGeometry": "true",
        "resultRecordCount": MAX_FEATURES,
    }
    response = _request_query(query_params)
    if response.get("type") != "FeatureCollection":
        raise IbamaEmbargoError("IBAMA não retornou coleção GeoJSON.")
    records = response.get("features")
    if not isinstance(records, list):
        raise IbamaEmbargoError("IBAMA não retornou lista de feições.")
    if response.get("exceededTransferLimit") or len(records) != count:
        raise IbamaEmbargoError("Lista do IBAMA incompleta ou divergente do total informado.")

    features: list[dict] = []
    geometries = []
    for item in records:
        if not isinstance(item, dict) or not isinstance(item.get("geometry"), dict):
            raise IbamaEmbargoError("Embargo sem geometria oficial: resultado inconclusivo.")
        try:
            polygon = shape(item["geometry"])
            if polygon.is_empty or not polygon.is_valid:
                raise ValueError("invalid embargo polygon")
            overlap = polygon.intersection(subject)
        except (ValueError, TypeError, GEOSException) as exc:
            raise IbamaEmbargoError("Polígono do embargo inválido.") from exc
        if overlap.is_empty:
            continue
        overlap_ha = _feature_area_ha(overlap)
        if overlap_ha <= 0:
            # Contact along a boundary is not a polygonal embargo area.
            continue
        props = item.get("properties") or {}
        if not isinstance(props, dict):
            raise IbamaEmbargoError("Atributos de embargo inválidos.")
        selected = {
            name: props.get(name) for name in (
                "num_tad", "serie_tad", "num_processo", "dat_embargo",
                "dat_ult_alteracao", "qtd_area_embargada", "tipo_area",
                "municipio", "uf", "num_auto_infracao", "des_tipo_bioma",
            ) if props.get(name) is not None
        }
        report_item = {
            "id": str(props.get("objectid") or item.get("id") or "")[:100],
            "term": str(props.get("num_tad") or "")[:30] or None,
            "process": str(props.get("num_processo") or "")[:60] or None,
            "declared_embargo_hectares": props.get("qtd_area_embargada"),
            "overlap_hectares": round(overlap_ha, 4),
            "attributes": selected,
        }
        if include_geometry:
            from shapely.geometry import mapping
            report_item["intersection_geometry"] = mapping(overlap)
        features.append(report_item)
        geometries.append(overlap)

    unique = _feature_area_ha(unary_union(geometries)) if geometries else 0.0
    property_area = _feature_area_ha(subject)
    return {
        "program": "IBAMA EMBARGOS",
        "layer": "base.adm_embargos_ibama_a",
        "layer_title": "Áreas embargadas — IBAMA/CENIMA",
        "source": "IBAMA — PAMGIA (ArcGIS REST)",
        "service_url": IBAMA_LAYER,
        "queried_at": datetime.now(timezone.utc).isoformat(),
        "status": "ANALYZED",
        "candidate_features": count,
        "interfering_features": len(features),
        "overlap_hectares": round(unique, 4),
        "overlap_percent": round(unique * 100 / property_area, 4) if property_area else None,
        "features": features,
        "method": (
            "ArcGIS REST envelope, comparação de contagem oficial, "
            "interseção geométrica e área geodésica; área única por união espacial."
        ),
        "warning": (
            "A interseção espacial de um embargo não demonstra responsabilidade do "
            "proprietário atual. O status e a vigência do termo devem ser "
            "confirmados no portal oficial do IBAMA."
        ),
    }
