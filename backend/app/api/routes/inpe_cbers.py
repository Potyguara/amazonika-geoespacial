"""Consulta limitada ao catálogo público STAC do INPE para o GEO-90.

Descoberta de cenas não equivale a validação posicional PS4.
Não faz download de GeoTIFF, não armazena credenciais nem certifica vértices.
"""
from __future__ import annotations

import json
import math
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi.responses import Response

from fastapi import APIRouter, Depends, HTTPException, Query
from app.services.auth import require_permission
from app.services.inpe_ps4_import import (
    COLLECTION as RGB_COLLECTION, L4_COLLECTION, fetch_inpe_item, examine_inpe_item,
)

router = APIRouter(
    prefix="/inpe-cbers",
    tags=["INPE CBERS-4A — descoberta de cenas"],
    dependencies=[Depends(require_permission("analysis.execute"))],
)

STAC_ROOT = os.environ.get("INPE_STAC_ROOT", "https://data.inpe.br/bdc/stac/v1").rstrip("/")
COLLECTIONS = {
    "ortho": "CB4A-WPM-L4-DN-1",
    "rgb": "CB4A-WPM-PCA-FUSED-1",
}
MAX_RESPONSE = 2_000_000


def validate_bbox(west: float, south: float, east: float, north: float) -> None:
    if not all(math.isfinite(v) for v in (west, south, east, north)):
        raise ValueError("Coordenadas não finitas.")
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("BBOX inválida; informe oeste, sul, leste e norte em WGS84.")
    if east - west > 1 or north - south > 1:
        raise ValueError("Área de pesquisa superior ao limite de 1 grau por eixo.")


def summarize_item(item: dict, collection: str) -> dict:
    props = item.get("properties") or {}
    assets = item.get("assets") or {}
    if not isinstance(assets, dict):
        assets = {}
    urls = {}
    for key, value in assets.items():
        if not isinstance(value, dict):
            continue
        url = value.get("href")
        if isinstance(url, str) and url.startswith("https://") and len(url) <= 2048:
            urls[key] = url
    raw_bbox = item.get("bbox")
    bbox = raw_bbox[:4] if isinstance(raw_bbox, list) and len(raw_bbox) >= 4 else None
    return {
        "id": str(item.get("id", ""))[:180],
        "collection": collection,
        "datetime": props.get("datetime") or props.get("start_datetime"),
        "bbox": bbox,
        "cloud_cover": props.get("eo:cloud_cover"),
        "gsd_m": props.get("gsd"),
        "thumbnail_url": next((v for k, v in urls.items() if "thumbnail" in k.lower()), None),
        "assets": sorted(urls.keys()),
        "stac_item_url": f"https://data.inpe.br/stac/browser/collections/{collection}/items/{item.get('id','')}",
        "ortho_status": "L4_DECLARED" if collection == COLLECTIONS["ortho"] else "DERIVED_FROM_L4",
        "ps4_status": "PENDING_ACCURACY_EVIDENCE",
    }


def search_scenes(bbox: tuple[float, float, float, float], kind: str, limit: int = 10) -> dict:
    validate_bbox(*bbox)
    if kind not in COLLECTIONS:
        raise ValueError("Coleção não permitida.")
    if not 1 <= limit <= 20:
        raise ValueError("Limite fora do intervalo permitido.")
    collection = COLLECTIONS[kind]
    params = urlencode({"bbox": ",".join(str(v) for v in bbox), "limit": limit})
    url = f"{STAC_ROOT}/collections/{collection}/items?{params}"
    request = Request(url, headers={"Accept": "application/geo+json, application/json", "User-Agent": "Amazonika-Geoespacial/1.0"})
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read(MAX_RESPONSE + 1)
    except HTTPError as exc:
        raise RuntimeError(f"INPE retornou HTTP {exc.code}.") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError("Catálogo INPE indisponível.") from exc
    if len(raw) > MAX_RESPONSE:
        raise RuntimeError("Resposta do INPE excedeu o tamanho permitido.")
    try:
        payload = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise RuntimeError("Resposta STAC inválida.") from exc
    features = payload.get("features")
    if not isinstance(features, list):
        raise RuntimeError("Resposta STAC sem lista de cenas.")
    return {
        "provider": "INPE / Brazil Data Cube",
        "collection": collection,
        "bbox": list(bbox),
        "scenes": [summarize_item(v, collection) for v in features[:limit] if isinstance(v, dict)],
        "certifiable": False,
        "warning": "Descoberta preliminar: PS4 depende de visibilidade da feição, relatório RMS da ortorretificação e avaliação pelo RT.",
    }


@router.get("/scenes")
def list_inpe_scenes(
    west: float = Query(..., ge=-180, le=180),
    south: float = Query(..., ge=-90, le=90),
    east: float = Query(..., ge=-180, le=180),
    north: float = Query(..., ge=-90, le=90),
    kind: str = Query("rgb", pattern="^(rgb|ortho)$"),
    limit: int = Query(10, ge=1, le=20),
):
    try:
        return search_scenes((west, south, east, north), kind, limit)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc

# GEO90B: disabled by default; only enable for a dedicated internal-only renderer.
TILE_ROOT = os.environ.get("INPE_COG_TILES_ROOT", "").rstrip("/")
TILE_SCENES = frozenset((
    "CBERS4A_WPM_PCA_RGB321_20261016_214_113",
    "CBERS4A_WPM_PCA_RGB321_20260815_214_113",
    "CBERS4A_WPM_PCA_RGB321_20260715_214_113",
))


@router.get("/tiles/{scene_id}/{z}/{x}/{y}.png")
def inpe_cbers_tile(scene_id: str, z: int, x: int, y: int):
    """Authenticated fixed-scene tile bridge. The browser never contacts the renderer."""
    if not TILE_ROOT:
        raise HTTPException(503, "Camada CBERS-4A não habilitada neste ambiente.")
    if scene_id not in TILE_SCENES:
        raise HTTPException(404, "Cena não habilitada para visualização.")
    if not 10 <= z <= 18 or not (0 <= x < 2 ** z and 0 <= y < 2 ** z):
        raise HTTPException(422, "XYZ inválido.")
    url = f"{TILE_ROOT}/tiles/{scene_id}/{z}/{x}/{y}.png"
    request = Request(url, headers={"Accept": "image/png", "User-Agent": "Amazonika-GEO90B/1.0"})
    try:
        with urlopen(request, timeout=150) as upstream:
            if upstream.status != 200 or upstream.headers.get_content_type() != "image/png":
                raise HTTPException(502, "Resposta inesperada do renderizador.")
            body = upstream.read(500_001)
    except HTTPError as exc:
        if exc.code in (404, 429):
            raise HTTPException(exc.code, "Tile fora da cena ou renderizador ocupado.") from exc
        raise HTTPException(502, "Renderizador temporariamente indisponível.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise HTTPException(502, "Falha de acesso ao renderizador privado.") from exc
    if len(body) > 500_000 or not body.startswith(bytes.fromhex("89504e470d0a1a0a")):
        raise HTTPException(502, "Tile PNG inválido ou excessivamente grande.")
    return Response(content=body, media_type="image/png", headers={
        "Cache-Control": "private, max-age=300",
        "X-Content-Type-Options": "nosniff",
    })


@router.get("/inspect/{kind}/{item_id}")
def inspect_cbers_scene(kind: str, item_id: str):
    """Examina o item real; não interpreta GSD como prova de acurácia."""
    if kind not in ("rgb", "ortho"):
        raise HTTPException(422, "Coleção não reconhecida.")
    collection = L4_COLLECTION if kind == "ortho" else RGB_COLLECTION
    try:
        return examine_inpe_item(fetch_inpe_item(item_id, collection))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
