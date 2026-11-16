"""Renderização autenticada de tiles do GeoTIFF efetivamente anexado ao PS4.

Usa GDAL CLI em arquivos temporários; nunca consulta o Google/CBERS como
substituto da ortoimagem. Restringe zoom, dimensões e concorrência.
"""
from __future__ import annotations

import os
import json
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


def _render_grayscale_tile(target: Path, temp: Path, env: dict) -> bytes:
    """Pancromático Int16 -> PNG RGBA de visualização, mantendo alpha real.

    Escala radiométrica por tile: melhora visualização local, mas não deve ser
    usada para análises quantitativas ou comparações radiométricas entre tiles.
    """
    stats = subprocess.run(
        ["gdalinfo", "-json", "-stats", str(target)],
        capture_output=True, text=True, check=False, timeout=20,
        env={**env, "GDAL_PAM_ENABLED": "NO"},
    )
    if stats.returncode:
        raise ValueError("Não foi possível calcular contraste pancromático.")
    bands = json.loads(stats.stdout).get("bands") or []
    metadata = (bands[0].get("metadata") or {}).get("") or {}
    try:
        low = float(metadata["STATISTICS_MINIMUM"])
        high = float(metadata["STATISTICS_MAXIMUM"])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValueError("Tile L4 sem estatísticas radiométricas válidas.") from exc
    if high <= low:
        # Pixel constante legítimo; não produzir intervalo -scale degenerado.
        high = low + 1
    grey = temp / "grayscale.png"
    alpha = temp / "alpha.png"
    for command, output in (
        (["gdal_translate", "-q", "-of", "PNG", "-ot", "Byte",
          "-b", "1", "-scale", str(low), str(high), "1", "255",
          str(target), str(grey)], grey),
        (["gdal_translate", "-q", "-of", "PNG", "-ot", "Byte",
          "-b", "2", str(target), str(alpha)], alpha),
    ):
        done = subprocess.run(
            command, check=False, capture_output=True, timeout=15, env=env,
        )
        if done.returncode or not output.is_file():
            raise ValueError("Falha na composição pancromática L4.")
    with Image.open(grey) as image, Image.open(alpha) as mask:
        value = image.convert("L")
        opacity = mask.convert("L")
        output = Image.merge("RGBA", (value, value, value, opacity))
        stream = BytesIO()
        output.save(stream, "PNG")
        return stream.getvalue()


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
                # GDAL converte Int16 -> PNG sem escala e satura os valores
                # pancromáticos; resultados podem ser opacos porém uniformes.
                # A transformação radiométrica altera SOMENTE o PNG de exibição.
                info_run = subprocess.run(
                    ["gdalinfo", "-json", str(target)],
                    check=False, capture_output=True, text=True,
                    timeout=15, env=env,
                )
                if info_run.returncode:
                    raise ValueError("Falha ao ler bandas do tile PS4.")
                info = json.loads(info_run.stdout)
                bands = info.get("bands") or []
                if len(bands) == 2 and bands[1].get("colorInterpretation") == "Alpha":
                    # Para L4 (uma banda + alpha), preservar a máscara de
                    # cobertura e aplicar contraste à banda Int16 separadamente.
                    result = _render_grayscale_tile(target, temp, env)
                    return result
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
