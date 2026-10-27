"""Google Map Tiles API adapter. Disabled until explicitly configured.

No Google API key or Google tile bytes are sent to the frontend except for
the authenticated, no-store response stream. Never use tiles for PDF export,
raster capture, analytics, prefetching or offline caching.
"""
from __future__ import annotations

import json
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from app.core.config import get_settings
from app.services.auth import get_current_user
from app.models.auth import User

router = APIRouter(prefix="/google-tiles", tags=["Bases cartográficas Google"])
_lock = threading.Lock()
_session: dict = {}


def _key() -> str:
    settings = get_settings()
    if not settings.google_map_tiles_enabled:
        raise HTTPException(503, "Map Tiles API desabilitada neste ambiente.")
    key = (settings.google_maps_api_key or "").strip()
    if not key:
        raise HTTPException(503, "Chave Google Maps ainda não configurada no servidor.")
    return key


def _fetch_google(path: str, params: dict, payload: dict | None = None):
    key = _key()
    # O endpoint de viewport usa /tile/v1/, diferente de createSession e 2dtiles.
    base_path = "tile/v1" if path == "viewport" else "v1"
    url = "https://tile.googleapis.com/" + base_path + "/" + path + "?" + urlencode({**params, "key": key})
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = Request(url, data=data, headers={"Content-Type": "application/json",
                                          "User-Agent": "Amazonika-Geoespacial/1.0"},
                  method="POST" if payload is not None else "GET")
    try:
        with urlopen(req, timeout=12) as resp:
            return resp.read(), resp.headers.get("Content-Type", "application/octet-stream")
    except HTTPError as exc:
        # Do not propagate provider responses, which may include sensitive URLs.
        raise HTTPException(502, f"Serviço Google Maps indisponível (HTTP {exc.code}).")
    except (URLError, TimeoutError):
        raise HTTPException(502, "Não foi possível consultar Google Map Tiles.")


def _current_session() -> dict:
    global _session
    with _lock:
        if _session.get("expiry", 0) > time.time()+120:
            return _session
        raw, _ = _fetch_google("createSession", {}, {
            "mapType": "satellite", "language": "pt-BR", "region": "BR",
        })
        payload = json.loads(raw)
        token = payload.get("session")
        if not token:
            raise HTTPException(502, "O Google não retornou token de sessão.")
        expiry = int(payload.get("expiry") or time.time()+3600)
        _session = {"token": token, "expiry": expiry}
        return _session


@router.get("/status")
def google_tiles_status(user: User = Depends(get_current_user)):
    settings = get_settings()
    return {"enabled": bool(settings.google_map_tiles_enabled and
                            (settings.google_maps_api_key or "").strip()),
            "pdf_export": False}


@router.get("/session")
def google_tiles_session(user: User = Depends(get_current_user)):
    state = _current_session()
    return Response(
        json.dumps({"session": state["token"], "expiry": state["expiry"]}),
        media_type="application/json", headers={"Cache-Control": "private, no-store"},
    )


@router.get("/tiles/{zoom}/{x}/{y}")
def google_tiles_tile(zoom: int, x: int, y: int,
                      user: User = Depends(get_current_user)):
    if not 0 <= zoom <= 22 or x < 0 or y < 0 or x >= (1 << zoom) or y >= (1 << zoom):
        raise HTTPException(422, "Coordenadas de bloco inválidas.")
    state = _current_session()
    data, mime = _fetch_google(f"2dtiles/{zoom}/{x}/{y}", {"session": state["token"]})
    if not mime.startswith("image/"):
        raise HTTPException(502, "Resposta inválida do serviço de imagens.")
    return Response(content=data, media_type=mime, headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })


@router.get("/attribution")
def google_tiles_attribution(north: float, south: float, east: float,
                             west: float, zoom: int,
                             user: User = Depends(get_current_user)):
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180 and 0 <= zoom <= 22):
        raise HTTPException(422, "Janela de mapa inválida.")
    state = _current_session()
    raw, _ = _fetch_google("viewport", {
        "session": state["token"], "zoom": zoom,
        "north": north, "south": south, "east": east, "west": west,
    })
    copyright_text = str(json.loads(raw).get("copyright") or "")
    return Response(json.dumps({"copyright": copyright_text}),
                    media_type="application/json",
                    headers={"Cache-Control": "private, no-store"})
