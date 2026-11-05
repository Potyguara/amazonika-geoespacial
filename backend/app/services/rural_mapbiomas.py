"""MapBiomas Collection 11 land-cover statistics through Google Earth Engine.

Read-only remote reduction. Does not download national raster imagery, persist
farm geometry or store Google service credentials. Disabled until a project
and a service account registered for Earth Engine are configured.

The 30 m classification is categorical. Class codes are not necessarily
consecutive and must not be inferred as a sequential palette.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from pathlib import Path

from shapely.geometry import shape
from shapely import get_num_coordinates

from app.core.config import get_settings

ASSET_ID = "projects/mapbiomas-public/assets/brazil/lulc/collection11/mapbiomas_brazil_collection11_coverage_v3"
COLLECTION = 11
RESOLUTION_M = 30
MIN_YEAR = 1985
MAX_YEAR = 2025
MAX_VERTICES = 25000
MAX_ENVELOPE_DEGREES = 0.8
MAX_PIXELS = 15_000_000

# Only officially verified class IDs are named here. All unknown classes are
# kept by code without being misclassified as forest, water or pasture.
CLASS_NAMES = {
    1: "Formação Florestal (agregação)",
    3: "Formação Florestal",
    4: "Formação Savânica",
    5: "Mangue",
    6: "Floresta Alagável",
    7: "Savana Alagada",
    10: "Vegetação Herbácea e Arbustiva (agregação)",
    11: "Campo Alagado e Área Pantanosa",
    12: "Formação Campestre",
    14: "Agropecuária (agregação)",
    15: "Pastagem",
    18: "Agricultura (agregação)",
    49: "Restinga Arbórea",
    50: "Restinga Herbácea ou Arbustiva",
    77: "Formação Herbácea Arbustiva",
    84: "Marisma",
}

CLASS_COLORS = {
    1: "#1f8d49", 3: "#1f8d49", 4: "#7dc975", 5: "#04381d",
    6: "#007785", 7: "#228c70", 10: "#d6bc74", 11: "#519799",
    12: "#d6bc74", 14: "#ffefc3", 15: "#edde8e", 18: "#e974ed",
    49: "#02d659", 50: "#ffaa5f", 77: "#86b074", 84: "#81dbbf",
}


class MapBiomasError(Exception):
    pass


def gee_configuration() -> dict:
    settings = get_settings()
    project = str(settings.gee_project_id or "").strip()
    email = str(settings.gee_service_account_email or "").strip()
    key_path = Path(settings.gee_service_account_key_file or "")
    enabled = bool(getattr(settings, "gee_enabled", False) and project and email and key_path.is_file())
    return {
        "enabled": enabled,
        "collection": COLLECTION,
        "asset_id": ASSET_ID,
        "min_year": MIN_YEAR,
        "max_year": MAX_YEAR,
        "resolution_m": RESOLUTION_M,
        "provider": "MapBiomas Brasil / Google Earth Engine",
        "message": (
            "Google Earth Engine configurado para consultas remotas."
            if enabled else
            "Google Earth Engine desabilitado ou sem credenciais. Habilite GEE_ENABLED "
            "somente após confirmar autorização, cotas e cobrança."
        ),
    }


def validate_geometry(geometry: dict):
    try:
        polygon = shape(geometry)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Perímetro rural inválido.") from exc
    if polygon.is_empty or not polygon.is_valid or polygon.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("MapBiomas requer perímetro poligonal válido.")
    if get_num_coordinates(polygon) > MAX_VERTICES:
        raise ValueError("Perímetro excede 25 mil vértices; simplifique para consulta raster.")
    bounds = polygon.bounds
    if bounds[2] - bounds[0] > MAX_ENVELOPE_DEGREES or bounds[3] - bounds[1] > MAX_ENVELOPE_DEGREES:
        raise ValueError("Imóvel extenso: divida em blocos ou utilize processamento assíncrono.")
    if not all(math.isfinite(value) for value in bounds):
        raise ValueError("Coordenadas não finitas.")
    return polygon


def _initialize_gee():
    configuration = gee_configuration()
    if not configuration["enabled"]:
        raise MapBiomasError("MapBiomas ainda não está habilitado: configure o Google Earth Engine.")
    try:
        import ee
    except ImportError as exc:
        raise MapBiomasError("Pacote Earth Engine Python não está instalado no backend.") from exc
    settings = get_settings()
    try:
        credentials = ee.ServiceAccountCredentials(
            settings.gee_service_account_email,
            settings.gee_service_account_key_file,
        )
        ee.Initialize(credentials, project=settings.gee_project_id)
    except Exception as exc:
        raise MapBiomasError("Earth Engine não pôde autenticar no projeto configurado.") from exc
    return ee


def _reduce_class_areas(ee, geometry: dict, year: int):
    roi = ee.Geometry(geometry, proj="EPSG:4326", geodesic=False)
    classified = ee.Image(ASSET_ID).select(f"classification_{year}").rename("classification")
    # Pixel area (m²) is summed by the categorical class band.
    pixel_ha = ee.Image.pixelArea().divide(10000).rename("area_ha")
    image = pixel_ha.addBands(classified)
    reducer = ee.Reducer.sum().group(groupField=1, groupName="class")
    return image.reduceRegion(
        reducer=reducer, geometry=roi,
        scale=RESOLUTION_M, maxPixels=MAX_PIXELS, bestEffort=False,
        tileScale=4,
    ).getInfo()


def _normalize_statistics(raw: object, year: int, geometric_ha: float) -> dict:
    if not isinstance(raw, dict) or not isinstance(raw.get("groups"), list):
        raise MapBiomasError("Earth Engine não retornou as estatísticas por classe.")
    group_items = raw["groups"]
    classes = []
    used_codes = set()
    for item in group_items:
        if not isinstance(item, dict):
            raise MapBiomasError("Estatísticas por classe inválidas.")
        try:
            code = int(item["class"])
            area = float(item["sum"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MapBiomasError("Classe ou área inválida no resultado Earth Engine.") from exc
        if not math.isfinite(area) or area < 0 or code in used_codes:
            raise MapBiomasError("Área negativa, não finita ou classe duplicada.")
        used_codes.add(code)
        classes.append({
            "code": code,
            "name": CLASS_NAMES.get(code, f"Classe {code} (consultar legenda da Coleção 11)"),
            "color": CLASS_COLORS.get(code),
            "area_hectares": round(area, 4),
        })
    total = sum(item["area_hectares"] for item in classes)
    if total <= 0:
        raise MapBiomasError("Nenhum pixel classificado nesta geometria; cobertura inconclusiva.")
    for item in classes:
        item["percent_classified"] = round(item["area_hectares"] * 100.0 / total, 3)
    classes.sort(key=lambda row: row["area_hectares"], reverse=True)
    return {
        "status": "ANALYZED",
        "provider": "MapBiomas Brasil / Google Earth Engine",
        "collection": COLLECTION,
        "asset_id": ASSET_ID,
        "year": year,
        "resolution_m": RESOLUTION_M,
        "queried_at": datetime.now(timezone.utc).isoformat(),
        "classified_area_hectares": round(total, 4),
        "geometry_area_hectares": round(geometric_ha, 4),
        "classes": classes,
        "method": (
            "Soma geodésica da área dos pixels de cada código classificado, "
            "redução remota do asset MapBiomas Coleção 11 no Google Earth Engine "
            "à resolução nominal de 30 metros."
        ),
        "warning": (
            "Classificação de sensoriamento remoto sujeita a resolução e incertezas. "
            "Os percentuais referem-se à área classificada, não à área cadastral. "
            "Não constitui laudo de desmatamento nem regularidade ambiental."
        ),
    }


def mapbiomas_preview(geometry: dict, year: int) -> dict:
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise ValueError(f"Ano indisponível na Coleção 11: informe {MIN_YEAR} a {MAX_YEAR}.")
    polygon = validate_geometry(geometry)
    from pyproj import Geod
    geometric_ha = abs(Geod(ellps="GRS80").geometry_area_perimeter(polygon)[0]) / 10000
    ee = _initialize_gee()
    try:
        raw = _reduce_class_areas(ee, geometry, year)
    except Exception as exc:
        raise MapBiomasError("Não foi possível obter as estatísticas do MapBiomas no Earth Engine.") from exc
    return _normalize_statistics(raw, year, geometric_ha)
