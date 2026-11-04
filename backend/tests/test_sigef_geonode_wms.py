"""Regressions for official SIGEF GeoNode WMS proxy routing (no external network)."""
from email.message import Message
from types import SimpleNamespace
from uuid import uuid4
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.routes import sources


class Database:
    def __init__(self, source):
        self.source = source
        self.closed = False

    def get(self, model, key):
        return self.source

    def close(self):
        self.closed = True


def request_with_query(query):
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/api/v1/sources/test/wms",
        "headers": [],
        "query_string": query.encode(),
        "server": ("localhost", 18001),
        "scheme": "http",
    })


def test_sigef_geonode_global_layer_routes_without_old_uf_suffix(monkeypatch):
    source = SimpleNamespace(
        name="SIGEF — Brasil", institution="INCRA",
        metadata_json={
            "wms_enabled": True, "wms_global": True,
            "wms_theme": "geonode:sigef_geo",
            "wms_fixed_layer": "geonode:sigef_geo",
            "wms_available_ufs": [],
            "wms_url": "https://geonodeincra.serpro.gov.br/geoserver/geonode/sigef_geo/ows",
        },
    )
    captured = {}

    class Upstream:
        def __init__(self):
            self.headers = Message()
            self.headers.add_header("Content-Type", "image/png")

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, n):
            return b"PNG-TEST"

    class Opener:
        def open(self, request, timeout):
            captured["url"] = request.full_url
            return Upstream()

    monkeypatch.setattr(sources, "build_opener", lambda *args: Opener())
    db = Database(source)
    response = sources.proxy_source_wms(
        uuid4(),
        request_with_query("uf=ap&SERVICE=WMS&REQUEST=GetMap&LAYERS=geonode%3Asigef_geo"),
        db,
    )
    parsed = urlsplit(captured["url"])
    assert parsed.hostname == "geonodeincra.serpro.gov.br"
    assert parsed.path == "/geoserver/geonode/sigef_geo/ows"
    assert parse_qs(parsed.query)["LAYERS"] == ["geonode:sigef_geo"]
    assert "tema=" not in parsed.query
    assert response.body == b"PNG-TEST"
    assert db.closed


def test_proxy_rejects_unapproved_hosts():
    source = SimpleNamespace(
        name="SIGEF — Brasil", institution="INCRA",
        metadata_json={
            "wms_enabled": True, "wms_global": True,
            "wms_fixed_layer": "geonode:sigef_geo",
            "wms_url": "https://example.org/evil",
        },
    )
    with pytest.raises(HTTPException) as error:
        sources.proxy_source_wms(uuid4(), request_with_query("uf=ap"), Database(source))
    assert error.value.status_code == 400
