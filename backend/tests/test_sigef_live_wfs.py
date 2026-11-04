"""Regression tests for live GeoNode SIGEF geometry retrieval."""
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from app.services import sigef_geonode_wfs as wfs


class FakeResponse:
    status = 200
    headers = {"Content-Type": "application/json"}

    def __init__(self, features):
        self.data = json.dumps({"type": "FeatureCollection", "features": features}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, count):
        return self.data[:count]


def fake_feature(uf_id=16):
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-51.1, -0.1], [-51.09, -0.1], [-51.09, -0.09], [-51.1, -0.1]]],
        },
        "properties": {"uf_id": uf_id, "parcela_codigo": "TESTE"},
    }


def test_live_wfs_ap_uses_ibge_filter_and_exact_bbox(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        return FakeResponse([fake_feature()])

    monkeypatch.setattr(wfs, "urlopen", fake_urlopen)
    features = wfs.fetch_sigef_geojson((-51.2, -0.2, -51.0, 0.0), "AP", purpose="analysis")
    query = parse_qs(urlsplit(captured["url"]).query)
    assert query["CQL_FILTER"] == ["uf_id=16"]
    assert query["BBOX"] == ["-51.2,-0.2,-51.0,0.0"]
    assert query["TYPENAME"] == ["sigef_geo"]
    assert len(features["features"]) == 1


def test_snap_rejects_large_bbox_before_network(monkeypatch):
    monkeypatch.setattr(wfs, "urlopen", lambda *args, **kwargs: pytest.fail("network"))
    with pytest.raises(ValueError, match="Área muito extensa"):
        wfs.fetch_sigef_geojson((-52, -1, -51, 0), "AP", purpose="snap")


def test_does_not_accept_truncated_feature_batch(monkeypatch):
    monkeypatch.setattr(wfs, "urlopen", lambda *args, **kwargs: FakeResponse([fake_feature()] * 501))
    with pytest.raises(ValueError, match="limite de feições"):
        wfs.fetch_sigef_geojson((-51.1, -0.1, -51.09, -0.09), "AP", purpose="snap")


def test_wfs_unavailable_is_not_silent_negative(monkeypatch):
    def upstream_down(*args, **kwargs):
        raise TimeoutError("INCRA indisponível")

    monkeypatch.setattr(wfs, "urlopen", upstream_down)
    with pytest.raises(TimeoutError):
        wfs.fetch_sigef_geojson((-51.1, -0.1, -51.09, -0.09), "AP", purpose="analysis")


def test_nationwide_query_omits_cql_filter(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        return FakeResponse([])

    monkeypatch.setattr(wfs, "urlopen", fake_urlopen)
    wfs.fetch_sigef_geojson((-51.1, -0.1, -51.09, -0.09), "ALL", purpose="analysis")
    assert "CQL_FILTER" not in parse_qs(urlsplit(captured["url"]).query)
