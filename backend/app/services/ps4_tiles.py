"""Renderização autenticada de tiles do GeoTIFF efetivamente anexado ao PS4.

Usa GDAL CLI em arquivos temporários; nunca consulta o Google/CBERS como
substituto da ortoimagem. Restringe zoom, dimensões e concorrência.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from io import BytesIO
from PIL import Image
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore

from shapely.geometry import box, shape

TILE_SIZE = 256
WORLD_HALF = 20037508.342789244
MIN_ZOOM = 0
MAX_ZOOM = 19
_TILE_SEMAPHORE = BoundedSemaphore(2)


def transparent_png_tile() -> bytes:
    """PNG transparente para tiles fora da ortoimagem, sem 404 em OpenLayers."""
    output = BytesIO()
    Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0)).save(output, "PNG")
    return output.getvalue()


def mercator_tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    if not (MIN_ZOOM <= z <= MAX_ZOOM) or not (0 <= x < 2**z) or not (0 <= y < 2**z):
        raise ValueError("Coordenadas XYZ fora do intervalo permitido.")
    size = 2 * WORLD_HALF / (2**z)
    minx = -WORLD_HALF + x * size
    maxy = WORLD_HALF - y * size
    return (minx, maxy - size, minx + size, maxy)


def tile_intersects_footprint(metadata: dict, z: int, x: int, y: int) -> bool:
    """Interseção geográfica real com o polígono devolvido pelo gdalinfo."""
    footprint = (metadata or {}).get("wgs84_extent")
    if not isinstance(footprint, dict):
        raise ValueError("GeoTIFF sem extensão WGS84 válida.")
    polygon = shape(footprint)
    if polygon.is_empty or not polygon.is_valid:
        raise ValueError("Cobertura do raster inválida.")
    # Teste de extensão preliminar via coordenadas da própria projeção XYZ.
    bounds = mercator_tile_bounds(z, x, y)
    from pyproj import Transformer
    projector = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    lon_min, lat_min = projector.transform(bounds[0], bounds[1])
    lon_max, lat_max = projector.transform(bounds[2], bounds[3])
    return polygon.intersects(box(lon_min, lat_min, lon_max, lat_max))


def render_png_tile(path: Path, z: int, x: int, y: int) -> bytes:
    """Gera PNG de 256x256 sem persistir tiles temporários no volume."""
    if not path.is_file():
        raise ValueError("Ortoimagem não localizada.")
    xmin, ymin, xmax, ymax = mercator_tile_bounds(z, x, y)
    if not _TILE_SEMAPHORE.acquire(timeout=12):
        raise RuntimeError("Processamento PS4 ocupado; reduza a velocidade de navegação.")
    try:
        with TemporaryDirectory(prefix="amazonika-ps4-tile-") as directory:
            temp = Path(directory)
            target = temp / "tile.tif"
            png = temp / "tile.png"
            env = {**os.environ, "GDAL_CACHEMAX": "32", "GDAL_NUM_THREADS": "1"}
            command = [
                "gdalwarp", "-q", "-overwrite",
                "-of", "GTiff", "-t_srs", "EPSG:3857",
                "-te", *(str(v) for v in (xmin, ymin, xmax, ymax)),
                "-ts", str(TILE_SIZE), str(TILE_SIZE),
                "-r", "bilinear", "-dstalpha",
                "-wm", "32", "-wo", "NUM_THREADS=1",
                str(path), str(target),
            ]
            try:
                warped = subprocess.run(
                    command, check=False, capture_output=True, timeout=25,
                    env=env,
                )
                if warped.returncode:
                    raise ValueError("Não foi possível reprojetar o tile da ortoimagem.")
                converted = subprocess.run(
                    ["gdal_translate", "-q", "-of", "PNG", str(target), str(png)],
                    check=False, capture_output=True, timeout=15, env=env,
                )
                if converted.returncode or not png.is_file():
                    raise ValueError("Falha ao converter o tile raster em PNG.")
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ValueError("Tempo limite ao processar o tile PS4.") from exc
            image = png.read_bytes()
            if not image.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("Resultado de tile não é PNG.")
            return image
    finally:
        _TILE_SEMAPHORE.release()
