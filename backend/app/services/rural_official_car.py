"""Official SICAR lookup by exact CAR code, without statewide downloads.

The public GeoServer exposes one per-UF polygon layer and cod_imovel. This
adapter always sends an equality predicate (never a broad state query).
No TLS verification bypass is performed. Service capabilities are tested
in homologation before any production deployment.
"""
from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from pyproj import Geod
from shapely import get_num_coordinates
from shapely.geometry import shape

SICAR_WFS = "https://geoserver.car.gov.br/geoserver/sicar/ows"
CAR_PATTERN = re.compile(r"^([A-Z]{2})-([0-9]{7})-([A-F0-9]{32})$")
CAR_UFS = frozenset(
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)
MAX_FEATURES = 2
MAX_VERTICES = 120_000
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
GEOD = Geod(ellps="GRS80")


class OfficialCarQueryError(Exception):
    pass


def normalize_car(code: str) -> str:
    cleaned = re.sub(r"\s+", "", code).upper()
    matched = CAR_PATTERN.fullmatch(cleaned)
    if not matched or matched.group(1) not in CAR_UFS:
        raise ValueError(
            "Código CAR inválido. Use UF-IBGE(7 dígitos)-identificador(32 caracteres hexadecimais)."
        )
    return cleaned


def _read_features(code: str) -> list[dict]:
    uf = code[:2].lower()
    layer = f"sicar:sicar_imoveis_{uf}"
    # WFS CQL equality avoids requesting the whole layer. Keep the URL fixed;
    # only the prevalidated CAR code is inserted into the predicate.
    params = {
        "SERVICE": "WFS", "VERSION": "1.0.0", "REQUEST": "GetFeature",
        "TYPENAME": layer, "OUTPUTFORMAT": "application/json",
        "CQL_FILTER": f"cod_imovel='{code}'", "MAXFEATURES": str(MAX_FEATURES),
        "SRSNAME": "EPSG:4326",
    }
    req = Request(
        SICAR_WFS + "?" + urlencode(params),
        headers={
            "User-Agent": "Amazonika-Geoespacial/1.0",
            "Accept": "application/json,application/geo+json",
        },
    )
    try:
        with urlopen(req, timeout=25) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            content_type = (response.headers.get("Content-Type") or "").lower()
    except (OSError, TimeoutError) as exc:
        raise OfficialCarQueryError("SICAR WFS indisponível ou inacessível.") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise OfficialCarQueryError("Resposta SICAR excedeu o limite seguro de transferência.")
    if "json" not in content_type:
        # XML may carry an OGC exception even when HTTP status is 200.
        try:
            root = ElementTree.fromstring(raw)
            details = [
                (node.text or "").strip()
                for node in root.iter()
                if node.tag.split("}")[-1] in {"ServiceException", "ExceptionText"}
                and (node.text or "").strip()
            ]
        except ElementTree.ParseError:
            details = []
        raise OfficialCarQueryError(
            "SICAR não retornou GeoJSON."
            + (f" Exceção OGC: {details[0][:180]}" if details else "")
        )
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise OfficialCarQueryError("GeoJSON inválido retornado pelo SICAR.") from exc
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise OfficialCarQueryError("SICAR não retornou coleção de feições.")
    features = payload.get("features")
    if not isinstance(features, list) or len(features) >= MAX_FEATURES:
        raise OfficialCarQueryError("CAR retornou múltiplos registros ou resultado inconclusivo.")
    return features


def _validate_car_feature(feature: dict, code: str) -> tuple[dict, object]:
    props = feature.get("properties") or {}
    if not isinstance(props, dict) or str(props.get("cod_imovel") or "").upper() != code:
        raise OfficialCarQueryError("Código CAR divergente na resposta oficial.")
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        raise OfficialCarQueryError("O SICAR não disponibilizou um perímetro poligonal.")
    try:
        polygon = shape(geometry)
    except (TypeError, ValueError) as exc:
        raise OfficialCarQueryError("Perímetro CAR inválido.") from exc
    if polygon.is_empty or not polygon.is_valid:
        raise OfficialCarQueryError("Perímetro CAR não possui geometria válida.")
    if get_num_coordinates(polygon) > MAX_VERTICES:
        raise OfficialCarQueryError("Perímetro CAR muito detalhado para análise direta.")
    return props, polygon


def _token(code: str, geometry: dict) -> str:
    canonical = json.dumps({"code": code, "geometry": geometry},
                           sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def fetch_car_candidate(raw_code: str) -> dict | None:
    code = normalize_car(raw_code)
    features = _read_features(code)
    if not features:
        return None
    feature = features[0]
    props, polygon = _validate_car_feature(feature, code)
    geometry = feature["geometry"]
    geometric_ha = abs(GEOD.geometry_area_perimeter(polygon)[0]) / 10000
    declared = props.get("area")
    try:
        declared_ha = float(declared) if declared not in (None, "") else None
    except (TypeError, ValueError):
        declared_ha = None
    return {
        "feature_id": _token(code, geometry),
        "source_id": None,
        "source_slug": "sicar-car-oficial",
        "source_name": "CAR — SICAR (oficial, WFS)",
        "institution": "Serviço Florestal Brasileiro",
        "name": str(props.get("cod_imovel") or code)[:180],
        "cadastral_code": code,
        "area_hectares": round(geometric_ha, 4),
        "declared_area_hectares": declared_ha,
        "vertex_count": get_num_coordinates(polygon),
        "reference_date": str(props.get("data_atualizacao") or "")[:50] or None,
        "imported_at": None,
        "uf": code[:2],
        "status": str(props.get("status_imovel") or "")[:30] or None,
        "retrieval": "OFFICIAL_CAR_WFS",
        "notice": "Área declarada e área geométrica podem diferir; cadastro CAR não comprova domínio.",
    }


def resolve_car_candidate(raw_code: str, feature_token: str) -> dict:
    code = normalize_car(raw_code)
    features = _read_features(code)
    if not features:
        raise OfficialCarQueryError("CAR não localizado na consulta oficial atual.")
    feature = features[0]
    props, polygon = _validate_car_feature(feature, code)
    if _token(code, feature["geometry"]) != feature_token:
        raise OfficialCarQueryError(
            "Geometria cadastral mudou desde a busca. Consulte novamente o código CAR."
        )
    return {
        "name": code, "source_name": "CAR — SICAR (oficial, WFS)",
        "source_slug": "sicar-car-oficial",
        "reference_date": str(props.get("data_atualizacao") or "")[:50] or None,
        "geometry": feature["geometry"],
        "status": props.get("status_imovel"),
        "area_declarada_ha": props.get("area"),
        "notice": "Perímetro do cadastro ambiental rural autodeclarado; não comprova propriedade ou regularidade.",
    }
