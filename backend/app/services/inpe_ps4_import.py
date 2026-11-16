"""Importação controlada de recorte CBERS-4A do catálogo STAC oficial.

O produto RGB fusionado deriva de L4; isto NÃO equivale à comprovação
de acurácia absoluta do limite PS4. O PDF/avaliação do RT permanecem exigidos.
"""
from __future__ import annotations

import ipaddress
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
from threading import BoundedSemaphore
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from app.services.ps4_assets import store_uploaded_asset

COLLECTION = "CB4A-WPM-PCA-FUSED-1"
STAC_BASE = "https://data.inpe.br/bdc/stac/v1"
MAX_ITEM_BYTES = 1_000_000
MAX_EXPORT_AREA_DEGREES = 0.025
MAX_OUTPUT_PIXELS = 3000 * 3000
_IMPORT_SEMAPHORE = BoundedSemaphore(1)
_ITEM_ID = re.compile(r"^CBERS4A_WPM_PCA_RGB321_\d{8}_\d{3}_\d{3}$")
_ALLOWED_ASSET_HOSTS = frozenset({
    "data.inpe.br", "bdc.inpe.br", "www.dpi.inpe.br",
})


def _allowed_asset_url(value: str) -> str:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https" or host not in _ALLOWED_ASSET_HOSTS
        or parsed.username or parsed.password or parsed.port not in (None, 443)
        or not parsed.path.lower().endswith((".tif", ".tiff"))
    ):
        raise ValueError(
            "A fonte GeoTIFF não está em um host INPE permitido para importação. "
            "Use o download manual ou avalie a configuração de origem."
        )
    return value


def fetch_inpe_item(item_id: str) -> dict:
    """Consulta item fixo na API oficial, sem aceitar URL fornecida pelo navegador."""
    if not _ITEM_ID.fullmatch(item_id):
        raise ValueError("Identificador CBERS-4A fusionado inválido.")
    url = f"{STAC_BASE}/collections/{COLLECTION}/items/{item_id}"
    request = Request(url, headers={
        "Accept": "application/json", "User-Agent": "Amazonika-GEO90/1.0",
    })
    try:
        with urlopen(request, timeout=20) as response:
            if urlparse(response.geturl()).hostname != "data.inpe.br":
                raise ValueError("Redirecionamento de metadados STAC não autorizado.")
            payload = response.read(MAX_ITEM_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("Consulta ao catálogo INPE indisponível.") from exc
    if len(payload) > MAX_ITEM_BYTES:
        raise ValueError("Item STAC excede o tamanho permitido.")
    try:
        item = json.loads(payload)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Item STAC inválido.") from exc
    if item.get("id") != item_id or item.get("collection") != COLLECTION:
        raise ValueError("Item STAC não corresponde à coleção solicitada.")
    return item


def examine_inpe_item(item: dict) -> dict:
    """Somente metadados e disponibilidade, nunca certificação PS4."""
    assets = item.get("assets") or {}
    target = next(
        (assets.get(key) for key in ("tci", "rgb") if isinstance(assets.get(key), dict)),
        None,
    )
    if not target:
        raise ValueError("Cena INPE não possui GeoTIFF RGB fusionado.")
    href = target.get("href", "")
    try:
        _allowed_asset_url(href)
        supported = True
        reason = None
    except ValueError as exc:
        supported = False
        reason = str(exc)
    props = item.get("properties") or {}
    return {
        "id": item["id"], "collection": item.get("collection"),
        "datetime": props.get("datetime"),
        "gsd_m": props.get("gsd"),
        "source_type": "INPE_STAC_L4_DERIVED_RGB_COG",
        "processing": "PCA_FUSION_FROM_CBERS4A_WPM_L4_DN",
        "asset_key": "tci" if assets.get("tci") is target else "rgb",
        "import_supported": supported,
        "reason": reason,
        "orthorectified_origin_declared": True,
        "absolute_accuracy_verified": False,
        "orthorectification_rms_m": None,
        "report_available": False,
        "warning": "Produto RGB derivado de L4 ortorretificado; "
                   "não foram demonstrados RMS nem precisão absoluta para PS4.",
    }


def validate_crop(bbox: tuple[float, float, float, float]) -> tuple[int, float]:
    w, s, e, n = bbox
    if not all(math.isfinite(v) for v in bbox) or not (
        -180 <= w < e <= 180 and -85 <= s < n <= 85
    ):
        raise ValueError("BBOX WGS84 inválida.")
    if e-w > MAX_EXPORT_AREA_DEGREES or n-s > MAX_EXPORT_AREA_DEGREES:
        raise ValueError(
            "Recorte PS4 maior que 0,025°; divida a área antes de importar."
        )
    lon, lat = (w+e)/2, (s+n)/2
    zone = int((lon+180)//6)+1
    if not 1 <= zone <= 60:
        raise ValueError("Zona UTM inválida.")
    epsg = (32600 if lat >= 0 else 32700) + zone
    # Aproximação conservadora do limite de pixels em 2 m, apenas para
    # orçamento de recursos. O GDAL é responsável pela transformação final.
    width = (e-w)*111_320*max(math.cos(math.radians(lat)), 0.2)/2
    height = (n-s)*111_320/2
    if width * height > MAX_OUTPUT_PIXELS:
        raise ValueError("Recorte excede orçamento de 9 milhões de pixels.")
    return epsg, 2.0


def import_inpe_crop(
    item: dict, bbox: tuple[float, float, float, float], user_id, piece_id,
) -> dict:
    """Recorta COG remoto por intervalo HTTP sem baixar cena de vários GB."""
    descriptor = examine_inpe_item(item)
    if not descriptor["import_supported"]:
        raise ValueError(descriptor["reason"])
    epsg, resolution = validate_crop(bbox)
    asset = item["assets"][descriptor["asset_key"]]
    href = _allowed_asset_url(asset["href"])
    if not _IMPORT_SEMAPHORE.acquire(blocking=False):
        raise RuntimeError("Já existe um recorte CBERS em preparação. Tente novamente.")
    try:
        with tempfile.TemporaryDirectory(prefix="amazonika-inpe-") as folder:
            output = Path(folder) / "crop.tif"
            env = {
                **os.environ,
                "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
                "GDAL_HTTP_MAX_RETRY": "2",
                "GDAL_HTTP_RETRY_DELAY": "1",
                "GDAL_CACHEMAX": "64",
                "GDAL_NUM_THREADS": "1",
            }
            command = [
                "gdalwarp", "-q", "-overwrite", "-of", "GTiff",
                "-t_srs", f"EPSG:{epsg}",
                "-te_srs", "EPSG:4326",
                "-te", *(str(c) for c in bbox),
                "-tr", str(resolution), str(resolution),
                "-r", "bilinear",
                "-srcnodata", "0", "-dstnodata", "0",
                "-co", "TILED=YES", "-co", "COMPRESS=DEFLATE",
                "-wm", "64", "-wo", "NUM_THREADS=1",
                "/vsicurl/" + href, str(output),
            ]
            try:
                result = subprocess.run(
                    command, env=env, capture_output=True, timeout=150,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise RuntimeError("GDAL não conseguiu acessar o COG remoto a tempo.") from exc
            if result.returncode or not output.is_file() or output.stat().st_size == 0:
                raise RuntimeError(
                    "Falha no recorte COG do INPE; verifique disponibilidade, "
                    "URL do ativo e cobertura da cena."
                )
            with output.open("rb") as source:
                saved = store_uploaded_asset(source, user_id, piece_id, "raster")
            return {
                "asset": saved,
                "provenance": {
                    "provider": "INPE / Brazil Data Cube",
                    "collection": COLLECTION,
                    "item_id": item["id"],
                    "asset_key": descriptor["asset_key"],
                    "source_href": href,
                    "crop_bbox_wgs84": list(bbox),
                    "target_epsg": epsg,
                    "pixel_size_m": resolution,
                    "source_type": descriptor["source_type"],
                    "origin_orthorectified": True,
                    "absolute_accuracy_verified": False,
                    "requires_rt_review": True,
                    "requires_orthorectification_report": True,
                },
            }
    finally:
        _IMPORT_SEMAPHORE.release()
