"""Test bounded official INCRA point lookup without making network requests."""
from unittest.mock import patch

import pytest

from app.services import rural_official_sigef as rural


def rectangle(left=-51.1, bottom=-0.1, right=-51.0, top=0.0):
    return {
        "type": "Polygon",
        "coordinates": [[
            [left, bottom], [right, bottom],
            [right, top], [left, top], [left, bottom],
        ]],
    }


def feature(code, geom=None):
    return {
        "type": "Feature",
        "id": f"sigef_geo.{code}",
        "geometry": geom if geom is not None else rectangle(),
        "properties": {
            "parcela_codigo": code,
            "nome_area": f"Parcela {code}",
            "uf_id": 16,
        },
    }


def mocked_wfs(items):
    return {"type": "FeatureCollection", "features": items}


def test_official_query_requires_polygon_covering_coordinate(monkeypatch):
    captured = {}

    def provider(bounds, uf, *, purpose):
        captured.update({"bounds": bounds, "uf": uf, "purpose": purpose})
        return mocked_wfs([
            feature("INNER"),
            feature("OUTSIDE", rectangle(-50.9, -0.1, -50.8, 0.0)),
        ])

    monkeypatch.setattr(rural, "fetch_sigef_geojson", provider)
    result = rural.locate_official_sigef(-0.05, -51.05)
    assert result["candidate_count"] == 1
    assert result["candidates"][0]["cadastral_code"] == "INNER"
    assert result["candidates"][0]["retrieval"] == "OFFICIAL_WFS"
    assert captured["uf"] == "ALL"
    assert captured["purpose"] == "snap"
    assert captured["bounds"][2] - captured["bounds"][0] <= 0.00201


def test_user_cannot_resolve_another_parcel_by_token(monkeypatch):
    monkeypatch.setattr(rural, "fetch_sigef_geojson",
                        lambda *args, **kwargs: mocked_wfs([feature("INNER")]))
    located = rural.locate_official_sigef(-0.05, -51.05)
    token = located["candidates"][0]["feature_id"]
    resolved = rural.resolve_official_sigef(-0.05, -51.05, token)
    assert resolved["name"] == "Parcela INNER"
    assert resolved["geometry"]["type"] == "Polygon"
    with pytest.raises(rural.OfficialSigefQueryError, match="não localizada"):
        rural.resolve_official_sigef(-0.05, -51.05, "0" * 64)


def test_change_in_remote_polygon_invalidates_old_token(monkeypatch):
    data = [feature("INNER")]
    monkeypatch.setattr(rural, "fetch_sigef_geojson",
                        lambda *args, **kwargs: mocked_wfs(data))
    token = rural.locate_official_sigef(-0.05, -51.05)["candidates"][0]["feature_id"]
    data[0] = feature("INNER", rectangle(-51.11, -0.11, -51.0, 0.0))
    with pytest.raises(rural.OfficialSigefQueryError):
        rural.resolve_official_sigef(-0.05, -51.05, token)


def test_upstream_error_cannot_be_misreported_as_no_candidates(monkeypatch):
    def fails(*args, **kwargs):
        raise TimeoutError("INCRA timeout")
    monkeypatch.setattr(rural, "fetch_sigef_geojson", fails)
    with pytest.raises(rural.OfficialSigefQueryError, match="timeout"):
        rural.locate_official_sigef(-0.05, -51.05)


def test_too_many_overlapping_parcels_is_inconclusive(monkeypatch):
    monkeypatch.setattr(rural, "fetch_sigef_geojson",
                        lambda *args, **kwargs: mocked_wfs([
                            feature(str(index)) for index in range(21)
                        ]))
    with pytest.raises(rural.OfficialSigefQueryError, match="Mais de 20"):
        rural.locate_official_sigef(-0.05, -51.05)


def test_invalid_polygon_is_not_used_for_cadastral_analysis(monkeypatch):
    broken = {
        "type": "Polygon",
        "coordinates": [[[-51.1, -0.1], [-51.0, 0], [-51.1, 0],
                          [-51.0, -0.1], [-51.1, -0.1]]],
    }
    monkeypatch.setattr(rural, "fetch_sigef_geojson",
                        lambda *args, **kwargs: mocked_wfs([feature("broken", broken)]))
    with pytest.raises(rural.OfficialSigefQueryError, match="inválida"):
        rural.locate_official_sigef(-0.05, -51.05)
