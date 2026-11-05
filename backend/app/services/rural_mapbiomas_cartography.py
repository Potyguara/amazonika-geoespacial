"""Bounded MapBiomas 2025 thematic thumbnail for preliminary PDF cartography.

A single remote Earth Engine thumbnail request produces actual class pixels,
masked to the independently verified cadastral polygon. No full-resolution
raster, image file, property geometry or Google token is persisted. This image
is a visual thematic preview, not a survey-grade georeferenced plan.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import math
from urllib.request import urlopen

from PIL import Image as PILImage
from pyproj import Geod

from app.services.rural_mapbiomas import (
    ASSET_ID, CLASS_COLORS, MAX_YEAR, MIN_YEAR, _initialize_gee, validate_geometry,
)

MAX_THUMB_SIDE = 640
MAX_THUMB_PIXELS = 350_000
MAX_THUMB_BYTES = 3 * 1024 * 1024
MAX_THUMB_AREA_HA = 1500
GEOD = Geod(ellps="GRS80")


@dataclass(frozen=True)
class ThematicThumbnail:
    png: bytes
    bounds: tuple[float, float, float, float]
    width: int
    height: int
    year: int
    class_codes: tuple[int, ...]


def _thumbnail_dimensions(bounds: tuple[float, float, float, float]) -> tuple[int, int]:
    west, south, east, north = bounds
    mid_lat = (south + north) / 2
    _, _, width_m = GEOD.inv(west, mid_lat, east, mid_lat)
    _, _, height_m = GEOD.inv(west, south, west, north)
    if width_m <= 0 or height_m <= 0 or not all(
        math.isfinite(x) for x in (width_m, height_m)
    ):
        raise ValueError("Extensão do mapa inválida.")
    ratio = width_m / height_m
    if ratio >= 1:
        width = MAX_THUMB_SIDE
        height = max(1, round(width / ratio))
    else:
        height = MAX_THUMB_SIDE
        width = max(1, round(height * ratio))
    if width * height > MAX_THUMB_PIXELS:
        factor = math.sqrt(MAX_THUMB_PIXELS / (width * height))
        width = max(1, math.floor(width * factor))
        height = max(1, math.floor(height * factor))
    return width, height


def fetch_mapbiomas_thematic_thumbnail(
    geometry: dict, *, year: int, class_codes: list[int],
) -> ThematicThumbnail:
    """Fetch only one bounded 8-bit PNG thumbnail from official EE class pixels."""
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise ValueError("Ano MapBiomas indisponível.")
    polygon = validate_geometry(geometry)
    area_ha = abs(GEOD.geometry_area_perimeter(polygon)[0]) / 10000
    if not 0 < area_ha <= MAX_THUMB_AREA_HA:
        raise ValueError("Área excede limite cartográfico de 1.500 ha.")
    codes = sorted(set(class_codes))
    if not codes or len(codes) > 40 or any(code not in CLASS_COLORS for code in codes):
        raise ValueError("Há classes sem cor oficial validada para este mapa.")
    bounds = tuple(float(v) for v in polygon.bounds)
    width, height = _thumbnail_dimensions(bounds)
    ee = _initialize_gee()
    roi = ee.Geometry(geometry, proj="EPSG:4326", geodesic=False)
    bbox = ee.Geometry.Rectangle(list(bounds), proj="EPSG:4326", geodesic=False)
    classified = ee.Image(ASSET_ID).select(f"classification_{year}")
    # Palette indexes start at 1; zero is transparent (outside ROI / no-data).
    indexed = classified.remap(codes, list(range(1, len(codes) + 1)), 0)
    colored = indexed.updateMask(indexed.neq(0)).clip(roi).visualize(
        min=1, max=len(codes),
        palette=[CLASS_COLORS[code] for code in codes],
        forceRgbOutput=True,
    )
    try:
        thumbnail_url = colored.getThumbURL({
            "region": bbox,
            "dimensions": f"{width}x{height}",
            "format": "png",
            "crs": "EPSG:4326",
        })
        # Token-bearing thumbnail URL is never logged or returned.
        with urlopen(thumbnail_url, timeout=45) as response:
            raw = response.read(MAX_THUMB_BYTES + 1)
    except Exception as exc:
        raise RuntimeError("Earth Engine não retornou a miniatura temática.") from exc
    if len(raw) > MAX_THUMB_BYTES or not raw.startswith(b"\\x89PNG\\r\\n\\x1a\\n"):
        raise ValueError("Miniatura temática inválida ou acima de 3 MB.")
    try:
        with PILImage.open(BytesIO(raw)) as picture:
            picture.verify()
        with PILImage.open(BytesIO(raw)) as picture:
            if picture.width > MAX_THUMB_SIDE or picture.height > MAX_THUMB_SIDE:
                raise ValueError("Miniatura excedeu a dimensão segura.")
            if picture.width * picture.height > MAX_THUMB_PIXELS:
                raise ValueError("Miniatura excedeu 350 mil pixels.")
            actual_width, actual_height = picture.size
    except (OSError, ValueError) as exc:
        raise ValueError("Arquivo PNG retornado não pôde ser validado.") from exc
    return ThematicThumbnail(
        png=raw, bounds=bounds, width=actual_width,
        height=actual_height, year=year, class_codes=tuple(codes),
    )
