"""Importação controlada de recorte CBERS-4A do catálogo STAC oficial.

O produto RGB fusionado deriva de L4; isto NÃO equivale à comprovação
de acurácia absoluta do limite PS4. O PDF/avaliação do RT permanecem exigidos.
"""
from __future__ import annotations

import hashlib
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
from app.core.config import get_settings
from defusedxml import ElementTree as SafeXML
from defusedxml.common import DefusedXmlException
from xml.etree.ElementTree import ParseError

COLLECTION = "CB4A-WPM-PCA-FUSED-1"
L4_COLLECTION = "CB4A-WPM-L4-DN-1"
COLLECTIONS = frozenset((COLLECTION, L4_COLLECTION))
STAC_BASE = "https://data.inpe.br/bdc/stac/v1"
MAX_ITEM_BYTES = 1_000_000
MAX_EXPORT_AREA_DEGREES = 0.05
MAX_OUTPUT_PIXELS = 3000 * 3000
_IMPORT_SEMAPHORE = BoundedSemaphore(1)
_ITEM_ID = re.compile(r"^CBERS4A_WPM_PCA_RGB321_\d{8}_\d{3}_\d{3}$")
_L4_ITEM_ID = re.compile(r"^CBERS_4A_WPM_\d{8}_\d{3}_\d{3}_L4$")
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


MAX_XML_BYTES = 2 * 1024 * 1024


def fetch_official_xml(item: dict, user_id, piece_id) -> dict:
    """Arquiva XML oficial com hash; não infere automaticamente acurácia."""
    assets = item.get("assets") or {}
    keys = sorted(k for k in assets if "xml" in k.lower())
    if not keys:
        return {"status": "NOT_LISTED"}
    key = next((k for k in keys if k.upper().startswith("BAND0")), keys[0])
    href = assets[key].get("href", "")
    parsed = urlparse(href)
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() not in _ALLOWED_ASSET_HOSTS
        or not parsed.path.lower().endswith(".xml")
        or parsed.username or parsed.password or parsed.port not in (None,443)
    ):
        return {"status": "SOURCE_NOT_ALLOWED", "asset_key": key}
    try:
        with urlopen(
            Request(href, headers={"Accept": "application/xml,text/xml",
                                    "User-Agent": "Amazonika-GEO90/1.0"}),
            timeout=20,
        ) as response:
            if (urlparse(response.geturl()).hostname or "").lower() not in _ALLOWED_ASSET_HOSTS:
                raise ValueError("Redirecionamento XML não autorizado.")
            data = response.read(MAX_XML_BYTES+1)
        if not data or len(data) > MAX_XML_BYTES:
            raise ValueError("XML oficial vazio ou excessivamente grande.")
        root = SafeXML.fromstring(data)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError,
            ParseError, DefusedXmlException) as exc:
        return {"status": "UNAVAILABLE", "asset_key": key,
                "reason": type(exc).__name__}
    digest = hashlib.sha256(data).hexdigest()
    storage = get_settings().storage_dir / "ps4" / str(user_id) / str(piece_id)
    storage.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = storage / f"inpe-metadata-{digest}.xml"
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(dir=storage, delete=False) as temp:
            temp_name = Path(temp.name)
            temp.write(data)
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name is not None:
            temp_name.unlink(missing_ok=True)
    # Apenas nomes dos campos potencialmente relevantes. Não exibir como RMS
    # aprovado: metadados XML podem descrever ajustes ou grandezas diferentes.
    candidate_names = sorted({
        element.tag.rsplit("}", 1)[-1][:80]
        for element in root.iter()
        if any(term in element.tag.lower() for term in (
            "rms", "accuracy", "precis", "ortho", "geometric", "error"
        ))
    })[:25]
    return {
        "status": "ARCHIVED_UNVERIFIED", "asset_key": key,
        "sha256": digest, "bytes": len(data),
        "source_href": href, "candidate_field_names": candidate_names,
        "absolute_accuracy_verified": False,
        "report_pdf_available": False,
    }


def verified_official_xml_path(user_id, piece_id, metadata: dict) -> Path:
    if metadata.get("status") != "ARCHIVED_UNVERIFIED":
        raise ValueError("Metadados XML não arquivados.")
    digest = metadata.get("sha256", "")
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("Identificador XML inválido.")
    path = (get_settings().storage_dir / "ps4" / str(user_id) /
            str(piece_id) / f"inpe-metadata-{digest}.xml")
    try:
        if path.stat().st_size > MAX_XML_BYTES or path.stat().st_size == 0:
            raise ValueError("Arquivo XML inconsistente.")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Integridade do XML de origem não comprovada.")
    except OSError as exc:
        raise ValueError("XML de origem não encontrado.") from exc
    return path


def fetch_inpe_item(item_id: str, collection: str = COLLECTION) -> dict:
    """Consulta item fixo na API oficial, sem aceitar URL fornecida pelo navegador."""
    if collection not in COLLECTIONS:
        raise ValueError("Coleção CBERS-4A não permitida.")
    expected = _L4_ITEM_ID if collection == L4_COLLECTION else _ITEM_ID
    if not expected.fullmatch(item_id):
        raise ValueError("Identificador CBERS-4A incompatível com a coleção.")
    url = f"{STAC_BASE}/collections/{collection}/items/{item_id}"
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
    if item.get("id") != item_id or item.get("collection") != collection:
        raise ValueError("Item STAC não corresponde à coleção solicitada.")
    return item


def examine_inpe_item(item: dict) -> dict:
    """Somente metadados e disponibilidade, nunca certificação PS4."""
    assets = item.get("assets") or {}
    collection = item.get("collection")
    if collection not in COLLECTIONS:
        raise ValueError("Coleção STAC não aceita para PS4.")
    preferred = ("BAND0", "BAND1") if collection == L4_COLLECTION else ("tci", "rgb")
    target = next(
        (assets.get(key) for key in preferred if isinstance(assets.get(key), dict)),
        None,
    )
    if not target:
        raise ValueError("Cena INPE sem GeoTIFF nas bandas suportadas.")
    href = target.get("href", "")
    try:
        _allowed_asset_url(href)
        supported = True
        reason = None
    except ValueError as exc:
        supported = False
        reason = str(exc)
    props = item.get("properties") or {}
    is_l4 = collection == L4_COLLECTION
    key = next(k for k in preferred if assets.get(k) is target)
    return {
        "id": item["id"], "collection": item.get("collection"),
        "datetime": props.get("datetime"),
        "gsd_m": props.get("gsd"),
        "source_type": "INPE_STAC_L4_ORTHORECTIFIED" if is_l4 else "INPE_STAC_L4_DERIVED_RGB_COG",
        "processing": "LEVEL_4_ORTHORECTIFIED" if is_l4 else "PCA_FUSION_FROM_CBERS4A_WPM_L4_DN",
        "asset_key": key,
        "metadata_assets": sorted(k for k in assets if "xml" in k.lower()),
        "import_supported": supported,
        "reason": reason,
        "orthorectified_origin_declared": True,
        "absolute_accuracy_verified": False,
        "orthorectification_rms_m": None,
        "report_available": False,
        "warning": ("Produto L4 declarado ortorretificado" if is_l4
                    else "Produto RGB fusionado derivado de L4 ortorretificado") +
                   "; não foram demonstrados RMS nem precisão absoluta para PS4.",
    }


def validate_crop(bbox: tuple[float, float, float, float]) -> tuple[int, float]:
    w, s, e, n = bbox
    if not all(math.isfinite(v) for v in bbox) or not (
        -180 <= w < e <= 180 and -85 <= s < n <= 85
    ):
        raise ValueError("BBOX WGS84 inválida.")
    if e-w > MAX_EXPORT_AREA_DEGREES or n-s > MAX_EXPORT_AREA_DEGREES:
        raise ValueError(
            "Recorte PS4 maior que 0,05°; divida a área antes de importar."
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
            xml = fetch_official_xml(item, user_id, piece_id)
            return {
                "asset": saved,
                "provenance": {
                    "provider": "INPE / Brazil Data Cube",
                    "collection": item["collection"],
                    "item_id": item["id"],
                    "asset_key": descriptor["asset_key"],
                    "source_href": href,
                    "crop_bbox_wgs84": list(bbox),
                    "target_epsg": epsg,
                    "pixel_size_m": resolution,
                    "source_type": descriptor["source_type"],
                    "technical_xml": xml,
                    "origin_orthorectified": True,
                    "absolute_accuracy_verified": False,
                    "requires_rt_review": True,
                    "requires_orthorectification_report": True,
                },
            }
    finally:
        _IMPORT_SEMAPHORE.release()
