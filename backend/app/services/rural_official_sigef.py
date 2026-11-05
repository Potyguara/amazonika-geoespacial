"""Identify current SIGEF parcels containing a coordinate without national downloads.

The GeoNode WFS does not accept BBOX and CQL_FILTER simultaneously. Reuse
the verified, bounded BBOX-only request and inspect the resulting polygon
geometries locally. A feature token is recomputed on resolution; clients
cannot supply an arbitrary geometry to this service.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from pyproj import Geod
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry

from app.services.sigef_geonode_wfs import fetch_sigef_geojson

# Restrict searches to a point-centered area of roughly 250 x 250 m
# (actual distance varies with latitude).
POINT_RADIUS_DEGREES = 0.001
MAX_OFFICIAL_CANDIDATES = 20
MAX_OFFICIAL_VERTICES = 120_000
_GEOD = Geod(ellps="GRS80")


class OfficialSigefQueryError(Exception):
    """The source is unavailable, incomplete, or inconsistent."""


def _feature_token(feature: dict) -> str:
    # Hash both the identifier and the geometry. A modified official parcel
    # invalidates the previous selection, rather than silently using stale data.
    data = {
        "id": feature.get("id"),
        "codigo": (feature.get("properties") or {}).get("parcela_codigo"),
        "geometry": feature.get("geometry"),
    }
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _polygon_and_properties(feature: dict) -> tuple[BaseGeometry, dict] | None:
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        return None
    polygon = shape(geometry)
    if polygon.is_empty or not polygon.is_valid:
        raise OfficialSigefQueryError("Geometria oficial inválida; não usar para diagnóstico.")
    if len(polygon.wkt) > 4_000_000:
        raise OfficialSigefQueryError("Parcela excessivamente complexa; utilize o perímetro cadastral.")
    props = feature.get("properties") or {}
    if not isinstance(props, dict):
        props = {}
    return polygon, props


def _bbox(latitude: float, longitude: float) -> tuple[float, float, float, float]:
    radius = POINT_RADIUS_DEGREES
    return (
        max(-180, longitude - radius), max(-90, latitude - radius),
        min(180, longitude + radius), min(90, latitude + radius),
    )


def _matching_features(latitude: float, longitude: float) -> list[tuple[dict, BaseGeometry, dict]]:
    point = Point(longitude, latitude)
    try:
        payload = fetch_sigef_geojson(_bbox(latitude, longitude), "ALL", purpose="snap")
    except (OSError, ValueError, TimeoutError) as exc:
        raise OfficialSigefQueryError(str(exc)[:280]) from exc
    found = []
    for item in payload.get("features") or []:
        parsed = _polygon_and_properties(item)
        if parsed is None:
            continue
        polygon, props = parsed
        if not polygon.covers(point):
            continue
        found.append((item, polygon, props))
        if len(found) > MAX_OFFICIAL_CANDIDATES:
            raise OfficialSigefQueryError(
                "Mais de 20 parcelas oficiais contêm o ponto; refinar a identificação cadastral."
            )
    return found


def locate_official_sigef(latitude: float, longitude: float) -> dict:
    matched = _matching_features(latitude, longitude)
    candidates = []
    for feature, polygon, attrs in matched:
        code = str(attrs.get("parcela_codigo") or feature.get("id") or "").strip()[:150]
        area_m2 = abs(_GEOD.geometry_area_perimeter(polygon)[0])
        candidates.append({
            "feature_id": _feature_token(feature),
            "source_id": None,
            "source_slug": "incra-sigef-brasil",
            "source_name": "SIGEF — Brasil (oficial, WFS)",
            "institution": "INCRA",
            "name": str(attrs.get("nome_area") or code or "Parcela SIGEF")[:180],
            "cadastral_code": code or None,
            "area_hectares": round(area_m2 / 10000, 4),
            "vertex_count": None,
            "reference_date": None,
            "imported_at": None,
            "uf_id": attrs.get("uf_id"),
            "retrieval": "OFFICIAL_WFS",
        })
    return {
        "coordinate": {"latitude": latitude, "longitude": longitude},
        "candidate_count": len(candidates),
        "has_more": False,
        "candidates": candidates,
        "point_only": len(candidates) == 0,
        "coverage": "GeoNode INCRA — SIGEF nacional, consulta WFS por coordenada (sem download nacional).",
        "notice": "Parcela oficial localizada por coincidência geométrica. Não constitui comprovação dominial ou de regularidade.",
    }


def resolve_official_sigef(latitude: float, longitude: float, token: str) -> dict:
    matches = _matching_features(latitude, longitude)
    for feature, polygon, attrs in matches:
        if _feature_token(feature) != token:
            continue
        if len(polygon.wkt) > 4_000_000:
            raise OfficialSigefQueryError("Geometria muito extensa para análise automática.")
        return {
            "feature_id": token,
            "name": str(attrs.get("nome_area") or attrs.get("parcela_codigo") or "Parcela SIGEF")[:180],
            "source_name": "SIGEF — Brasil (oficial, WFS)",
            "source_slug": "incra-sigef-brasil",
            "reference_date": None,
            "uf_id": attrs.get("uf_id"),
            "geometry": feature["geometry"],
            "notice": "Geometria SIGEF recuperada diretamente do serviço oficial no momento da consulta.",
        }
    raise OfficialSigefQueryError(
        "Parcela não localizada na consulta oficial atual; localize novamente antes de analisar."
    )
