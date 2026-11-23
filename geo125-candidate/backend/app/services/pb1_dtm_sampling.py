"""Amostragem pontual do MDT numérico PB1 com GDAL, em coordenadas WGS84."""
from __future__ import annotations

import math
import subprocess
from pathlib import Path


def sample_pb1_dtm(path: Path, longitude: float, latitude: float, nodata: float | None = None) -> float:
    if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
        raise ValueError("Longitude/latitude fora do intervalo válido.")
    try:
        result = subprocess.run(
            ["gdallocationinfo", "-wgs84", "-valonly", str(path),
             f"{longitude:.10f}", f"{latitude:.10f}"],
            capture_output=True, text=True, check=False, timeout=25,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("GDAL indisponível para amostragem do MDT.") from exc
    if result.returncode != 0:
        raise ValueError("Não foi possível amostrar o MDT nesta posição.")
    rows = result.stdout.strip().splitlines()
    if len(rows) != 1:
        raise ValueError("MDT sem valor numérico único no vértice.")
    try:
        value = float(rows[0])
    except ValueError as exc:
        raise ValueError("Valor MDT inválido.") from exc
    if not math.isfinite(value) or (nodata is not None and abs(value - nodata) < 1e-8):
        raise ValueError("Amostra MDT é NoData ou não finita.")
    return value
