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
from functools import lru_cache
from math import isfinite

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


@lru_cache(maxsize=32)
def _source_stretch(source_name: str, modified_ns: int) -> tuple[float, float]:
    """Uma única escala visual por imagem; evita tiles em tabuleiro."""
    env = {**os.environ, "GDAL_PAM_ENABLED": "NO", "GDAL_CACHEMAX": "32"}
    info = subprocess.run(
        ["gdalinfo", "-json", "-approx_stats", source_name],
        capture_output=True, text=True, timeout=40, check=False, env=env,
    )
    if info.returncode:
        raise ValueError("Não foi possível obter estatísticas globais do GeoTIFF.")
    bands = json.loads(info.stdout).get("bands") or []
    if not bands:
        raise ValueError("GeoTIFF sem bandas para visualização.")
    band = bands[0]
    stats = (band.get("metadata") or {}).get("") or {}
    low = float(stats.get("STATISTICS_MINIMUM", band.get("minimum", "nan")))
    high = float(stats.get("STATISTICS_MAXIMUM", band.get("maximum", "nan")))
    if not (isfinite(low) and isfinite(high)):
        raise ValueError("GeoTIFF sem estatísticas globais válidas.")
    if high <= low:
        high = low + 1
    return low, high


def _render_grayscale_tile(target: Path, temp: Path, env: dict,
                           source: Path) -> bytes:
    """Mesmo contraste para TODOS os tiles da imagem real.

    Modifica somente os PNGs de visualização, não os dados raster.
    """
    low, high = _source_stretch(str(source), source.stat().st_mtime_ns)
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

def _render_pb1_rgb_tile(target: Path, temp: Path, env: dict,
                         source: Path) -> bytes:
    """RGB com contraste global por banda e alfa do recorte.

    GeoTIFF de visualização pode conter RGB de 8/16 bits. Renderizar com
    escala global por imagem; jamais modificar o produto original.
    """
    info_run = subprocess.run(
        ["gdalinfo", "-json", "-approx_stats", str(source)],
        capture_output=True, text=True, timeout=40, check=False,
        env={**env, "GDAL_PAM_ENABLED": "NO"},
    )
    if info_run.returncode:
        raise ValueError("Não foi possível ler estatísticas do RGB oficial.")
    bands = json.loads(info_run.stdout).get("bands") or []
    if len(bands) < 3:
        raise ValueError("RGB PB1 requer três bandas de imagem.")
    channel_images = []
    for index in range(3):
        band = bands[index]
        stats = (band.get("metadata") or {}).get("") or {}
        low = float(stats.get("STATISTICS_MINIMUM", band.get("minimum", "nan")))
        high = float(stats.get("STATISTICS_MAXIMUM", band.get("maximum", "nan")))
        if not (isfinite(low) and isfinite(high)):
            raise ValueError("RGB PB1 sem estatísticas radiométricas.")
        if high <= low:
            high = low + 1
        dest = temp / f"channel-{index + 1}.png"
        result = subprocess.run(
            ["gdal_translate", "-q", "-of", "PNG", "-ot", "Byte",
             "-b", str(index+1), "-scale", str(low), str(high), "0", "255",
             str(target), str(dest)],
            capture_output=True, timeout=15, check=False, env=env,
        )
        if result.returncode or not dest.is_file():
            raise ValueError("Falha ao renderizar canal RGB PB1.")
        with Image.open(dest) as img:
            channel_images.append(img.convert("L").copy())
    alpha_file = temp / "rgb-alpha.png"
    result = subprocess.run(
        ["gdal_translate", "-q", "-of", "PNG", "-ot", "Byte",
         "-b", "4", str(target), str(alpha_file)],
        capture_output=True, timeout=15, check=False, env=env,
    )
    if result.returncode or not alpha_file.is_file():
        raise ValueError("Falha na máscara de transparência RGB PB1.")
    with Image.open(alpha_file) as mask:
        rgba = Image.merge("RGBA", (*channel_images, mask.convert("L")))
        stream = BytesIO()
        rgba.save(stream, "PNG")
        return stream.getvalue()


def render_png_tile(path: Path, z: int, x: int, y: int, mode: str = "auto") -> bytes:
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
                if mode == "pb1_color":
                    if len(bands) != 4:
                        raise ValueError("RGB PB1 requer três canais e máscara alfa.")
                    return _render_pb1_rgb_tile(target, temp, env, path)
                if mode == "pb1_dtm":
                    if len(bands) != 2:
                        raise ValueError("MDT PB1 requer banda única e máscara alfa.")
                    return _render_grayscale_tile(target, temp, env, path)
                if len(bands) == 2 and bands[1].get("colorInterpretation") == "Alpha":
                    # Para L4 (uma banda + alpha), preservar a máscara de
                    # cobertura e aplicar contraste à banda Int16 separadamente.
                    result = _render_grayscale_tile(target, temp, env, path)
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
