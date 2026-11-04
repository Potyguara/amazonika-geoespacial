"""Bounded, official national SIGEF GeoNode WFS vector queries.

The WMS is visual only. Analysis and snapping always require real WFS
geometries. Never silently use an image or an older local snapshot as a
substitute for failed official WFS queries.
"""
from __future__ import annotations

import json
import math
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import geopandas as gpd

SIGEF_WFS = "https://geonodeincra.serpro.gov.br/geoserver/geonode/sigef_geo/ows"
IBGE_UF = {
    "AC": 12, "AL": 27, "AP": 16, "AM": 13, "BA": 29, "CE": 23,
    "DF": 53, "ES": 32, "GO": 52, "MA": 21, "MT": 51, "MS": 50,
    "MG": 31, "PA": 15, "PB": 25, "PR": 41, "PE": 26, "PI": 22,
    "RJ": 33, "RN": 24, "RS": 43, "RO": 11, "RR": 14, "SC": 42,
    "SP": 35, "SE": 28, "TO": 17,
}


def validate_bbox(bounds: tuple[float, float, float, float], max_span: float) -> None:
    if len(bounds) != 4 or not all(math.isfinite(x) for x in bounds):
        raise ValueError("BBOX inválido.")
    x1, y1, x2, y2 = bounds
    if not (-180 <= x1 < x2 <= 180 and -90 <= y1 < y2 <= 90):
        raise ValueError("BBOX fora dos limites geográficos.")
    if x2 - x1 > max_span or y2 - y1 > max_span:
        raise ValueError("Área muito extensa para consulta WFS. Aproxime o mapa ou divida a análise.")


def _request_geojson(bounds, uf: str | None, limit: int, timeout: int) -> list:
    if uf is not None and uf.upper() != "ALL" and uf.upper() not in IBGE_UF:
        raise ValueError("UF inválida para consulta SIGEF.")
    if not 1 <= limit <= 5001:
        raise ValueError("Limite de feições inválido.")
    params = {
        "SERVICE": "WFS",
        "VERSION": "1.0.0",
        "REQUEST": "GetFeature",
        "TYPENAME": "sigef_geo",
        "OUTPUTFORMAT": "application/json",
        "BBOX": ",".join(str(v) for v in bounds),
        "MAXFEATURES": str(limit),
    }
    url = SIGEF_WFS + "?" + urlencode(params)
    request = Request(url, headers={
        "User-Agent": "Amazonika-Geoespacial/1.0",
        "Accept": "application/json,application/geo+json",
    })
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise ValueError(f"SIGEF WFS retornou HTTP {response.status}")
        raw = response.read(12 * 1024 * 1024 + 1)
        content_type = (response.headers.get("Content-Type") or "").lower()
    if len(raw) > 12 * 1024 * 1024:
        raise ValueError("Resposta SIGEF WFS excedeu 12 MB.")
    if "json" not in content_type:
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(raw)
            errors = [str(node.text or "").strip() for node in root.iter()
                      if node.tag.split("}")[-1] in {"ServiceException", "ExceptionText"}]
            if errors:
                raise ValueError("SIGEF WFS rejeitou a consulta: " + errors[0][:260])
        except ET.ParseError:
            pass
        raise ValueError("SIGEF WFS não retornou GeoJSON (tipo: " + content_type[:90] + ").")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ValueError("Resposta SIGEF WFS não contém FeatureCollection.")
    features = payload.get("features")
    if not isinstance(features, list):
        raise ValueError("Resposta SIGEF WFS sem lista de feições.")
    if len(features) >= limit:
        raise ValueError("Consulta SIGEF WFS atingiu o limite de feições; área deve ser reduzida para não omitir parcelas.")
    expected_uf = IBGE_UF.get(uf.upper()) if uf and uf.upper() != "ALL" else None
    validated = [item for item in features if isinstance(item, dict) and item.get("geometry")]
    if expected_uf is not None:
        # The official GetFeature form verified on the VPS only used BBOX.
        # Filter returned candidates locally, after the completeness check.
        # Reject features missing uf_id rather than assuming a state.
        missing_uf = [item for item in validated if item.get("properties", {}).get("uf_id") is None]
        if missing_uf:
            raise ValueError("SIGEF WFS retornou parcelas sem uf_id; filtragem estadual inconclusiva.")
        validated = [
            item for item in validated
            if str(item.get("properties", {}).get("uf_id")) == str(expected_uf)
        ]
    return validated


def fetch_sigef_geojson(bounds, uf: str | None, *, purpose: str) -> dict:
    max_span = 0.15 if purpose == "snap" else 1.0
    limit = 501 if purpose == "snap" else 5001
    validate_bbox(bounds, max_span=max_span)
    features = _request_geojson(bounds, uf, limit, timeout=35 if purpose == "snap" else 75)
    return {"type": "FeatureCollection", "features": features, "source": "GeoNode INCRA WFS", "snapshot": False}


def fetch_sigef_frame(bounds, uf: str | None):
    payload = fetch_sigef_geojson(bounds, uf, purpose="analysis")
    features = payload["features"]
    if not features:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    frame = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
    if frame.crs is None:
        frame = frame.set_crs("EPSG:4326")
    return frame.to_crs("EPSG:4674")
