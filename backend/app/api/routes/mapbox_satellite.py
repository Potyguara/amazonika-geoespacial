"""Authenticated optional Mapbox Satellite raster gateway (online viewing only)."""
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen, Request

from fastapi import APIRouter, Depends, HTTPException, Response

from app.core.config import get_settings
from app.services.auth import get_current_user
from app.models.auth import User

router = APIRouter(prefix="/mapbox-satellite", tags=["Mapbox Satellite"])


@router.get("/status")
def mapbox_status(user: User = Depends(get_current_user)):
    cfg = get_settings()
    return {
        "enabled": bool(cfg.mapbox_satellite_enabled and
                        (cfg.mapbox_access_token or "").strip()),
        "pdf_export": False,
        "attribution": "© Mapbox | Imagery providers as specified by Mapbox",
    }


@router.get("/tiles/{z}/{x}/{y}")
def satellite_tile(z: int, x: int, y: int, user: User = Depends(get_current_user)):
    cfg = get_settings()
    token = (cfg.mapbox_access_token or "").strip()
    if not cfg.mapbox_satellite_enabled or not token:
        raise HTTPException(status_code=503, detail="Mapbox Satellite não configurado.")
    if not 0 <= z <= 22 or not 0 <= x < 2 ** z or not 0 <= y < 2 ** z:
        raise HTTPException(status_code=422, detail="Tile fora dos limites.")
    url = (
        f"https://api.mapbox.com/v4/mapbox.satellite/{z}/{x}/{y}.jpg90?"
        + urlencode({"access_token": token})
    )
    try:
        with urlopen(Request(url, headers={"User-Agent": "Amazonika-Geoespacial/1.0"}), timeout=12) as result:
            raw = result.read()
            content_type = result.headers.get("Content-Type", "")
    except HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Mapbox indisponível (HTTP {error.code}).")
    except (URLError, TimeoutError):
        raise HTTPException(status_code=502, detail="Falha de comunicação com Mapbox.")
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=502, detail="Resposta inválida da Mapbox.")
    return Response(content=raw, media_type=content_type,
                    headers={"Cache-Control": "private, no-store",
                             "X-Content-Type-Options": "nosniff"})
