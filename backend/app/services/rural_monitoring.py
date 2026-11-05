"""Read-only TerraBrasilis monitoring adapter (public PRODES/DETER WFS).

No nationwide download: retrieve layer metadata, then request up to
MAX_FEATURES candidates within a small geometry envelope and clip in memory.
PRODES polygons and DETER warnings are monitoring indicators, NOT legal
determinations of irregularity. No output is cached persistently.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from time import monotonic
import json
import math
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from pyproj import Geod
from shapely.geometry import shape
from shapely import get_num_coordinates
from shapely.errors import GEOSException
from shapely.ops import unary_union

WFS_URL = "https://terrabrasilis.dpi.inpe.br/geoserver/ows"
MAX_FEATURES = 1001  # reserve the final record to detect truncation
MAX_RESPONSE = 15 * 1024 * 1024
MAX_SPAN_DEGREES = 0.35
MAX_SUBJECT_VERTICES = 25000
MAX_CATALOG_LAYERS = 400
_LAYER_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
_GEOD = Geod(ellps="GRS80")


class MonitoringQueryError(Exception):
    """Remote monitoring data unavailable, invalid or incomplete."""


def _request(parameters: dict[str, str], max_bytes: int, timeout: int = 25) -> bytes:
    request = Request(
        WFS_URL + "?" + urlencode(parameters),
        headers={
            "User-Agent": "Amazonika-Geoespacial/1.0",
            "Accept": "application/json,application/xml,text/xml,*/*",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(max_bytes + 1)
            content_type = (response.headers.get("Content-Type") or "").lower()
    except (OSError, TimeoutError) as exc:
        raise MonitoringQueryError("TerraBrasilis indisponível no momento.") from exc
    if len(raw) > max_bytes:
        raise MonitoringQueryError("Resposta ultrapassou o limite de transferência.")
    if "html" in content_type:
        raise MonitoringQueryError("TerraBrasilis retornou página HTML em vez de dados oficiais.")
    return raw


def _parse_xml(raw: bytes) -> ET.Element:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise MonitoringQueryError("XML oficial inválido.") from exc
    errors = [
        (element.text or "").strip()
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] in {"ServiceException", "ExceptionText"}
        and (element.text or "").strip()
    ]
    if errors:
        raise MonitoringQueryError("WFS oficial recusou a consulta: " + errors[0][:200])
    return root


def _find_tag(element: ET.Element, tag: str) -> str | None:
    for node in element:
        if node.tag.rsplit("}", 1)[-1] == tag:
            return (node.text or "").strip() or None
    return None


@lru_cache(maxsize=1)
def _catalog_snapshot() -> tuple[datetime, list[dict]]:
    params = {"service": "WFS", "version": "1.0.0", "request": "GetCapabilities"}
    root = _parse_xml(_request(params, max_bytes=3 * 1024 * 1024))
    if root.tag.rsplit("}", 1)[-1] != "WFS_Capabilities":
        raise MonitoringQueryError("Resposta não contém capacidades WFS.")
    layers: list[dict] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "FeatureType":
            continue
        name = _find_tag(element, "Name")
        title = _find_tag(element, "Title") or name or ""
        if not name or not _LAYER_RE.fullmatch(name):
            continue
        identifier = (name + " " + title).lower()
        kind = "DETER" if "deter" in identifier else "PRODES" if "prodes" in identifier else None
        if kind is None:
            continue
        layers.append({
            "name": name, "title": title[:240], "program": kind,
        })
    if not layers:
        raise MonitoringQueryError("Nenhuma camada PRODES/DETER foi publicada nas capacidades consultadas.")
    if len(layers) > MAX_CATALOG_LAYERS:
        # Do not silently truncate authorization catalogue. Need an explicit
        # curated list rather than arbitrary server-side layer selection.
        raise MonitoringQueryError("Catálogo muito amplo; requer seleção controlada de camadas.")
    return datetime.now(timezone.utc), layers


_CATALOG_VALID_UNTIL = 0.0


def monitoring_catalog() -> dict:
    """One capability fetch per process, refreshed every 30 minutes."""
    global _CATALOG_VALID_UNTIL
    if monotonic() >= _CATALOG_VALID_UNTIL:
        _catalog_snapshot.cache_clear()
        fetched, layers = _catalog_snapshot()
        _CATALOG_VALID_UNTIL = monotonic() + 1800
    else:
        fetched, layers = _catalog_snapshot()
    return {
        "source": "INPE — TerraBrasilis (WFS público)",
        "url": WFS_URL,
        "checked_at": fetched.isoformat(),
        "layers": layers,
        "message": "Camadas publicadas não garantem cobertura sobre o imóvel selecionado.",
    }


def validate_subject(geometry: dict):
    try:
        subject = shape(geometry)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Geometria do imóvel inválida.") from exc
    if subject.geom_type not in {"Polygon", "MultiPolygon"} or not subject.is_valid or subject.is_empty:
        raise ValueError("A análise de desmatamento exige polígono válido.")
    if get_num_coordinates(subject) > MAX_SUBJECT_VERTICES:
        raise ValueError("Geometria excessivamente detalhada para consulta rápida.")
    bounds = subject.bounds
    if len(bounds) != 4 or not all(math.isfinite(v) for v in bounds):
        raise ValueError("Extensão espacial inválida.")
    if bounds[2] - bounds[0] > MAX_SPAN_DEGREES or bounds[3] - bounds[1] > MAX_SPAN_DEGREES:
        raise ValueError("Perímetro excede a janela de consulta inicial; é necessário processamento em blocos.")
    return subject


def _feature_area_ha(geometry) -> float:
    polygons = []
    if geometry.is_empty:
        return 0.0
    if geometry.geom_type == "Polygon":
        polygons = [geometry]
    elif geometry.geom_type == "MultiPolygon":
        polygons = list(geometry.geoms)
    elif geometry.geom_type == "GeometryCollection":
        return sum(_feature_area_ha(part) for part in geometry.geoms)
    return sum(abs(_GEOD.geometry_area_perimeter(poly)[0]) / 10000.0 for poly in polygons)


def monitoring_preview(layer_name: str, geometry: dict) -> dict:
    snapshot = monitoring_catalog()
    selected = next((entry for entry in snapshot["layers"] if entry["name"] == layer_name), None)
    if selected is None or not _LAYER_RE.fullmatch(layer_name):
        raise ValueError("Camada não consta do catálogo WFS oficial validado.")

    subject = validate_subject(geometry)
    minx, miny, maxx, maxy = subject.bounds
    params = {
        "service": "WFS", "version": "1.0.0", "request": "GetFeature",
        "typeName": layer_name, "outputFormat": "application/json",
        "bbox": f"{minx:.8f},{miny:.8f},{maxx:.8f},{maxy:.8f}",
        "maxFeatures": str(MAX_FEATURES),
    }
    raw = _request(params, MAX_RESPONSE, timeout=45)
    try:
        decoded = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        if raw.lstrip().startswith(b"<"):
            _parse_xml(raw)  # raise any OGC error, if present
        raise MonitoringQueryError("TerraBrasilis não retornou GeoJSON.") from exc
    if not isinstance(decoded, dict) or decoded.get("type") != "FeatureCollection":
        raise MonitoringQueryError("Resposta GeoJSON inválida.")
    records = decoded.get("features")
    if not isinstance(records, list):
        raise MonitoringQueryError("Lista de feições ausente.")
    if len(records) >= MAX_FEATURES - 1:
        raise MonitoringQueryError("Consulta atingiu o limite; recorte menor necessário para evitar omissões.")

    matches: list[dict] = []
    clipped_geometries = []
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("geometry"), dict):
            raise MonitoringQueryError(
                "A resposta PRODES/DETER contém feição sem geometria; "
                "não é possível assegurar completude."
            )
        try:
            vector = shape(record["geometry"])
            if vector.is_empty or not vector.is_valid:
                raise ValueError("invalid geometry")
            intersection = vector.intersection(subject)
        except (TypeError, ValueError, GEOSException) as exc:
            raise MonitoringQueryError("GeoJSON contém feição geométrica inválida.") from exc
        if intersection.is_empty:
            continue
        area = _feature_area_ha(intersection)
        if area <= 0:
            continue
        clipped_geometries.append(intersection)
        attrs = record.get("properties") or {}
        safe_attrs = {
            str(key)[:70]: str(value)[:120]
            for key, value in attrs.items()
            if value is not None and isinstance(value, (int, float, str, bool))
            and not any(term in str(key).lower() for term in ("cpf", "cnpj", "email", "telefone"))
        }
        matches.append({
            "id": str(record.get("id") or "")[:120],
            "overlap_hectares": round(area, 4),
            "attributes": dict(list(safe_attrs.items())[:14]),
        })
    union = unary_union(clipped_geometries) if clipped_geometries else None
    overlap = _feature_area_ha(union) if union is not None else 0.0
    subject_area = _feature_area_ha(subject)
    return {
        "program": selected["program"],
        "layer": selected["name"],
        "layer_title": selected["title"],
        "source": "INPE — TerraBrasilis",
        "status": "ANALYZED",
        "candidate_features": len(records),
        "interfering_features": len(matches),
        "overlap_hectares": round(overlap, 4),
        "overlap_percent": round(overlap * 100 / subject_area, 4) if subject_area else None,
        "features": matches,
        "method": "WFS BBOX, interseção geométrica exata e área geodésica GRS80; sem importação nacional.",
        "warning": "Polígonos PRODES/DETER são indicadores de monitoramento; não constituem prova automática de infração ambiental.",
    }
