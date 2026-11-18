"""Armazenamento privado e validação estrutural de arquivos PS4."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import BinaryIO
from uuid import UUID

from app.core.config import get_settings
from pyproj import CRS

MAX_RASTER_BYTES = 256 * 1024 * 1024
MAX_REPORT_BYTES = 25 * 1024 * 1024
CHUNK = 1024 * 1024


def _root(user_id: UUID, piece_id: UUID) -> Path:
    return get_settings().storage_dir / "ps4" / str(user_id) / str(piece_id)


def stored_file_path(user_id: UUID, piece_id: UUID, kind: str, digest: str) -> Path:
    if kind not in ("raster", "report", "pb1_color", "pb1_dtm", "ps1_ortho", "ps1_dtm", "ps1_report"):
        raise ValueError("Tipo de arquivo não suportado.")
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("Hash inválido.")
    return _root(user_id, piece_id) / f"{kind}-{digest}{'.tif' if kind not in ('report', 'ps1_report') else '.pdf'}"


def _raster_info(path: Path) -> dict:
    try:
        result = subprocess.run(
            ["gdalinfo", "-json", str(path)],
            capture_output=True, text=True, check=False, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Não foi possível analisar o GeoTIFF com GDAL.") from exc
    if result.returncode != 0:
        raise ValueError("GeoTIFF inválido ou incompatível com GDAL.")
    try:
        info = json.loads(result.stdout)
        if info.get("driverShortName") != "GTiff":
            raise ValueError("O raster deve ser um GeoTIFF.")
        if not info.get("coordinateSystem", {}).get("wkt"):
            raise ValueError("O GeoTIFF não possui sistema de referência definido.")
        if not info.get("geoTransform") or not info.get("bands"):
            raise ValueError("O GeoTIFF não possui georreferenciamento utilizável.")
        width, height = info.get("size", [0, 0])
        if width < 2 or height < 2:
            raise ValueError("Dimensões inválidas da imagem orbital.")
        raster_crs = CRS.from_wkt(info["coordinateSystem"]["wkt"])
        epsg = raster_crs.to_epsg()
        # Rótulos de proveniência embutidos no TIFF são informativos, não
        # comprovação jurídica de origem/PEC. Nunca deduzir classe pela escala.
        labels = info.get("metadata") or {}
        intrinsic = labels.get("") if isinstance(labels.get(""), dict) else {}
        tags = {}
        for key in ("TIFFTAG_IMAGEDESCRIPTION", "TIFFTAG_DOCUMENTNAME",
                    "TIFFTAG_COPYRIGHT", "TIFFTAG_ARTIST"):
            value = intrinsic.get(key)
            if isinstance(value, str) and value.strip():
                tags[key] = value.strip()[:500]
        vertical = raster_crs if raster_crs.is_vertical else next(
            (part for part in raster_crs.sub_crs_list if part.is_vertical), None
        )
        return {
            "width": width, "height": height,
            "crs_wkt": info["coordinateSystem"]["wkt"],
            "crs_authority": f"EPSG:{epsg}" if epsg is not None else None,
            "geo_transform": info["geoTransform"],
            "wgs84_extent": info.get("wgs84Extent"),
            "driver": "GTiff",
            "embedded_source_tags": tags,
            "vertical_crs_name": vertical.name if vertical else None,
            "bands": [{"band": i + 1, "type": band.get("type"),
                       "no_data_value": band.get("noDataValue")}
                      for i, band in enumerate(info.get("bands", []))],
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Metadados geoespaciais ausentes ou inválidos.") from exc


def store_uploaded_asset(
    source: BinaryIO, user_id: UUID, piece_id: UUID, kind: str
) -> dict:
    if kind not in ("raster", "report", "pb1_color", "pb1_dtm", "ps1_ortho", "ps1_dtm", "ps1_report"):
        raise ValueError("Tipo inválido.")
    root = _root(user_id, piece_id)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    max_bytes = MAX_REPORT_BYTES if kind in ("report", "ps1_report") else MAX_RASTER_BYTES
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(dir=root, prefix=".upload-", delete=False) as temp:
            temp_name = Path(temp.name)
            digest = hashlib.sha256()
            total = 0
            first = b""
            tail = b""
            while True:
                block = source.read(CHUNK)
                if not block:
                    break
                if not first:
                    first = block[:16]
                tail = (tail + block)[-2048:]
                total += len(block)
                if total > max_bytes:
                    raise ValueError("Arquivo excede o limite de tamanho da modalidade.")
                digest.update(block)
                temp.write(block)
            temp.flush()
            os.fsync(temp.fileno())
        if not total:
            raise ValueError("Arquivo vazio.")
        metadata = {}
        if kind not in ("report", "ps1_report"):
            if first[:4] not in (b"II*\x00", b"MM\x00*",
                                 b"II+\x00", b"MM\x00+"):
                raise ValueError("Arquivo não corresponde a TIFF/BigTIFF.")
            metadata = _raster_info(temp_name)
            bands = metadata.get("bands", [])
            if kind in ("pb1_color", "ps1_ortho") and len(bands) < 3:
                raise ValueError("PB1 Color requer GeoTIFF RGB com pelo menos três bandas.")
            if kind in ("pb1_dtm", "ps1_dtm") and (
                len(bands) != 1 or bands[0].get("type") not in ("Float32", "Float64", "Int16", "Int32")
            ):
                raise ValueError("PB1 MDT requer uma banda numérica de elevação, sem RGB.")
        else:
            if not first.startswith(b"%PDF-") or b"%%EOF" not in tail:
                raise ValueError("Relatório PDF inválido ou incompleto.")
        sha = digest.hexdigest()
        destination = stored_file_path(user_id, piece_id, kind, sha)
        os.replace(temp_name, destination)
        temp_name = None
        return {
            "sha256": sha, "size_bytes": total, "kind": kind,
            "metadata": metadata,
        }
    finally:
        if temp_name is not None:
            temp_name.unlink(missing_ok=True)


def exists_matching(user_id: UUID, piece_id: UUID, record: dict) -> bool:
    """Reconfere bytes no disco; registro de snapshot isolado não é prova."""
    try:
        path = stored_file_path(user_id, piece_id, record["kind"], record["sha256"])
        h = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(CHUNK), b""):
                h.update(chunk)
        return h.hexdigest() == record["sha256"]
    except (OSError, KeyError, ValueError, TypeError):
        return False
