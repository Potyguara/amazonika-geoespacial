"""Read-only public GeoNode catalogue metadata for the national SIGEF layer.

The catalogue's last_updated timestamp describes the GeoNode resource record,
not necessarily the date of its latest vector feature or SIGEF certification.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from urllib.request import Request, urlopen

CATALOGUE_URL = "https://geonodeincra.serpro.gov.br/catalogue/#/dataset/1"
API_URL = "https://geonodeincra.serpro.gov.br/api/v2/datasets/1/"
_LOCK = threading.Lock()
_CACHE: dict = {"expires": 0.0, "result": None}


def _valid_iso(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    try:
        datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return None
    return candidate


def parse_sigef_catalogue_metadata(payload: dict) -> dict:
    """Only accept an explicit resource-modification timestamp."""
    candidates: list[dict] = []
    for key in ("dataset", "resource"):
        if isinstance(payload.get(key), dict):
            candidates.append(payload[key])
    candidates.append(payload)
    for data in candidates:
        name = str(data.get("alternate") or data.get("name") or "")
        title = str(data.get("title") or "")
        if name and "sigef" not in name.lower() and "sigef" not in title.lower():
            # Avoid accidentally using an unrelated catalog entry.
            continue
        for field in ("last_updated", "last_modified", "modified", "date_modified"):
            stamp = _valid_iso(data.get(field))
            if stamp:
                return {
                    "last_modified": stamp,
                    "timestamp_field": field,
                    "catalogue_url": CATALOGUE_URL,
                    "meaning": "modificacao_registro_catalogo",
                    "available": True,
                }
    return {
        "last_modified": None,
        "timestamp_field": None,
        "catalogue_url": CATALOGUE_URL,
        "meaning": "modificacao_registro_catalogo",
        "available": False,
    }


def get_sigef_catalogue_metadata(force: bool = False) -> dict:
    now = time.monotonic()
    with _LOCK:
        cached = _CACHE["result"]
        if cached is not None and not force and now < _CACHE["expires"]:
            return dict(cached)
    result = None
    try:
        req = Request(
            API_URL,
            headers={
                "User-Agent": "Amazonika-Geoespacial/1.0",
                "Accept": "application/json",
            },
        )
        with urlopen(req, timeout=12) as response:
            if response.status != 200 or "json" not in (response.headers.get("Content-Type") or "").lower():
                raise ValueError("Resposta não é JSON do catálogo")
            raw = response.read(512_001)
            if len(raw) > 512_000:
                raise ValueError("Metadados ultrapassam o limite")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("Estrutura de metadados inválida")
        result = parse_sigef_catalogue_metadata(payload)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        result = parse_sigef_catalogue_metadata({})
    result["source"] = "GeoNode INCRA — catálogo de dados"
    with _LOCK:
        _CACHE.update({"result": result, "expires": time.monotonic() + (900 if result["available"] else 120)})
    return dict(result)
