"""Diagnóstico próprio da imagem PS4, sem afirmar RMS ou certificação.

Inspeciona um GeoTIFF previamente armazenado e seus metadados GDAL.
A resolução de pixel é nominal e NÃO representa precisão posicional.
"""
from __future__ import annotations

from math import hypot, isfinite
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore
import os
import subprocess
from PIL import Image, ImageFilter, ImageStat

_ANALYSIS_SEMAPHORE = BoundedSemaphore(1)

from shapely.geometry import Point, shape


def diagnose_ps4_raster(metadata: dict, vertices: list[dict]) -> dict:
    crs = str(metadata.get("crs_authority") or "").strip().upper()
    transform = metadata.get("geo_transform") or []
    width = metadata.get("width")
    height = metadata.get("height")
    if (not crs or len(transform) != 6 or
            not isinstance(width, int) or width < 2 or
            not isinstance(height, int) or height < 2):
        raise ValueError("Metadados georreferenciados incompletos.")
    values = [float(v) for v in transform]
    if not all(isfinite(v) for v in values):
        raise ValueError("Transformação afim raster inválida.")
    # Escala apenas em unidade projetada métrica (ex.: UTM).
    from pyproj import CRS
    spatial_ref = CRS.from_user_input(crs)
    linear_metre = bool(spatial_ref.is_projected and
                        spatial_ref.axis_info and
                        all(abs(axis.unit_conversion_factor - 1) < 1e-9
                            for axis in spatial_ref.axis_info[:2]))
    px = hypot(values[1], values[4]) if linear_metre else None
    py = hypot(values[2], values[5]) if linear_metre else None
    footprint_raw = metadata.get("wgs84_extent")
    if not isinstance(footprint_raw, dict):
        raise ValueError("GeoTIFF sem polígono de cobertura WGS84.")
    footprint = shape(footprint_raw)
    if footprint.is_empty or not footprint.is_valid or footprint.area <= 0:
        raise ValueError("Cobertura da imagem inválida.")
    outside = []
    for point in vertices:
        lon, lat = point.get("longitude"), point.get("latitude")
        if (not isinstance(lon, (float, int)) or not isfinite(lon) or
                not isinstance(lat, (float, int)) or not isfinite(lat)):
            raise ValueError("Vértice com coordenadas inválidas.")
        if not footprint.buffer(1e-9).covers(Point(lon, lat)):
            outside.append(str(point.get("name") or "V sem nome"))
    return {
        "status": "RASTER_STRUCTURALLY_VALID" if not outside else "COVERAGE_INCOMPLETE",
        "accuracy_status": "UNVERIFIED",
        "crs": crs, "width": width, "height": height,
        "pixel_size_x_m": round(px, 4) if px is not None else None,
        "pixel_size_y_m": round(py, 4) if py is not None else None,
        "vertices_checked": len(vertices),
        "vertices_inside": len(vertices) - len(outside),
        "vertices_outside": outside,
        "horizontal_rms_m": None,
        "sigma_lat_m": None, "sigma_lon_m": None,
        "warnings": [
            "Tamanho do pixel/GSD não comprova precisão posicional absoluta.",
            "Cobertura geométrica e integridade do GeoTIFF não geram RMS nem sigmas.",
            "PS4 permanece preliminar até comprovação de acurácia e revisão RT.",
        ],
    }


def analyze_raster_visual(path: Path) -> dict:
    """Amostra real do raster, sem dados externos e sem presumir acurácia.

    Parâmetros meramente radiométricos. Não estimam EMQ/sigmas e não
    avaliam nuvens com garantia científica.
    """
    from app.services.ps4_tiles import _source_stretch

    if not path.is_file():
        raise ValueError("Imagem privada não disponível para análise.")
    if not _ANALYSIS_SEMAPHORE.acquire(timeout=3):
        raise RuntimeError("Análise da imagem ocupada. Tente novamente.")
    try:
        low, high = _source_stretch(str(path), path.stat().st_mtime_ns)
        with TemporaryDirectory(prefix="ps4-visual-") as directory:
            image_path = Path(directory) / "analysis.png"
            env = {**os.environ, "GDAL_CACHEMAX": "32",
                   "GDAL_NUM_THREADS": "1", "GDAL_PAM_ENABLED": "NO"}
            args = [
                "gdal_translate", "-q", "-of", "PNG", "-ot", "Byte",
                "-b", "1", "-outsize", "256", "256", "-r", "bilinear",
                "-scale", str(low), str(high), "1", "255",
                str(path), str(image_path),
            ]
            try:
                run = subprocess.run(args, capture_output=True, check=False,
                                     env=env, timeout=25)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ValueError("Falha ou tempo excedido na amostragem da imagem.") from exc
            if run.returncode or not image_path.is_file():
                raise ValueError("Não foi possível amostrar a banda orbital.")
            with Image.open(image_path) as raster:
                sample = raster.convert("L")
                histogram = sample.histogram()
                count = sum(histogram)
                if count <= 0:
                    raise ValueError("Amostra radiométrica vazia.")
                # Média de gradiente por pixel em amostra reduzida.
                edges = sample.filter(ImageFilter.FIND_EDGES)
                edge_mean = ImageStat.Stat(edges).mean[0]
                contrast_sd = ImageStat.Stat(sample).stddev[0]
                clipped = sum(histogram[:4]) + sum(histogram[252:])
                result = {
                    "status": "ANALYZED",
                    "sample_width_px": sample.width,
                    "sample_height_px": sample.height,
                    "global_stretch_min": round(low, 3),
                    "global_stretch_max": round(high, 3),
                    "grayscale_stddev": round(contrast_sd, 2),
                    "edge_mean": round(edge_mean, 2),
                    "extreme_brightness_pct": round(100 * clipped / count, 2),
                    "quality_basis": "DIAGNOSTICO_RADIOMETRICO_EXPLORATORIO",
                    "positional_accuracy_m": None,
                    "sigma_e_m": None,
                    "sigma_n_m": None,
                    "warnings": [
                        "Indicadores radiométricos não determinam nitidez posicional certificável.",
                        "Amostra reduzida não identifica automaticamente nuvens, sombras ou erro orbital.",
                        "Não há RMS/EMQ independente: precisão PS4 permanece NÃO COMPROVADA.",
                    ],
                }
                return result
    finally:
        _ANALYSIS_SEMAPHORE.release()
