"""Offline API contract for layer attribute search.

No real database, no WFS, no paid service. Source/field whitelisting and
official CAR error/geometry results must be independent of rendering.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from app.api.routes import layer_search as search


def test_field_filter_prevents_sensitive_keys():
    class Db:
        def execute(self, *_args, **_kwargs):
            return SimpleNamespace(all=lambda: [({
                "cod_imovel": "AP-...",
                "num_processo": "123/2020",
                "nome": "Área",
                "cpf": "DO-NOT-RETURN",
                "proprietario": "DO-NOT-RETURN",
                "email": "DO-NOT-RETURN",
            },)])
    fields = search._fields(Db(), uuid4())
    assert "cod_imovel" in fields
    assert "num_processo" in fields
    assert "cpf" not in fields
    assert "proprietario" not in fields
    assert "email" not in fields


def test_inactive_source_returns_404_before_query():
    class Db:
        def get(self, *_args):
            return SimpleNamespace(is_active=False)
    with pytest.raises(HTTPException) as exc:
        search._current_version(Db(), uuid4())
    assert exc.value.status_code == 404


def test_no_ready_vector_does_not_claim_wms_is_searchable():
    class Db:
        def get(self, *_args):
            return SimpleNamespace(is_active=True, id=uuid4())
        def scalar(self, *_args):
            return None
    with pytest.raises(HTTPException) as exc:
        search._current_version(Db(), uuid4())
    assert exc.value.status_code == 409
    assert "WMS" in exc.value.detail


def test_official_car_uses_validated_geometry(monkeypatch):
    car = "AP-1600238-047B060C8AF84B3CB46946155615281E"
    polygon = {"type": "Polygon", "coordinates": [[
        [-51.102, .51], [-51.101, .51], [-51.101, .511],
        [-51.102, .511], [-51.102, .51],
    ]]}
    monkeypatch.setattr(search, "fetch_car_candidate", lambda code: {
        "feature_id": "temporary-token", "name": code,
        "area_hectares": 1.2, "reference_date": None,
    })
    monkeypatch.setattr(search, "resolve_car_candidate", lambda code, token: {
        "geometry": polygon,
    })
    result = search.find_official_car(car_code=car)
    assert len(result["results"]) == 1
    assert result["results"][0]["geometry"]["type"] == "Polygon"
    assert result["results"][0]["bbox"][0] == -51.102


def test_car_remote_error_is_503_not_empty(monkeypatch):
    monkeypatch.setattr(search, "fetch_car_candidate", lambda _: (
        (_ for _ in ()).throw(search.OfficialCarQueryError("timeout"))
    ))
    with pytest.raises(HTTPException) as exc:
        search.find_official_car(
            car_code="AP-1600238-047B060C8AF84B3CB46946155615281E"
        )
    assert exc.value.status_code == 503


def test_car_no_match_is_empty_after_successful_lookup(monkeypatch):
    monkeypatch.setattr(search, "fetch_car_candidate", lambda _: None)
    result = search.find_official_car(
        car_code="AP-1600238-047B060C8AF84B3CB46946155615281E"
    )
    assert result["results"] == []
