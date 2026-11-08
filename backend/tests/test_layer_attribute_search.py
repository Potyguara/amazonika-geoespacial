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


def test_anm_rejects_injection_and_invalid_process():
    with pytest.raises(HTTPException) as exc:
        search.find_official_anm_process(process_number="850123/2020' OR 1=1")
    assert exc.value.status_code == 422


def test_anm_returns_official_geojson_and_fixed_source(monkeypatch):
    import json
    from io import BytesIO

    class Response:
        headers = {"Content-Type": "application/geo+json"}
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, size):
            return json.dumps({
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "id": "ANM-1",
                    "geometry": {"type": "Polygon", "coordinates": [[
                        [-51.2, 0], [-51.1, 0], [-51.1, 0.1],
                        [-51.2, 0.1], [-51.2, 0],
                    ]]},
                    "properties": {
                        "PROCESSO": "850123/2020", "NUMERO": 850123,
                        "ANO": 2020, "FASE": "Pesquisa",
                        "NOME": "Não deve ser retornado",
                    },
                }],
            }).encode()
    called = []
    def fake_urlopen(request, timeout, context):
        assert context.verify_mode != 0
        assert context.check_hostname
        called.append(request.full_url)
        return Response()
    monkeypatch.setattr(search, "urlopen", fake_urlopen)
    result = search.find_official_anm_process(process_number="850.123/2020")
    assert len(result["results"]) == 1
    assert result["results"][0]["properties"]["FASE"] == "Pesquisa"
    assert "NOME" not in result["results"][0]["properties"]
    assert "geo.anm.gov.br" in called[0]
    assert "PROCESSO%3D%27850123%2F2020%27" in called[0]
    assert "FeatureServer%2F0" not in called[0]
    assert "/FeatureServer/0/query?" in called[0]



def test_anm_accepts_process_with_and_without_dot():
    import re
    for value in ("850.123/2020", "850123/2020"):
        matched = search.ANM_PROCESS_PATTERN.fullmatch(value)
        assert matched is not None
        assert matched.groups() == ("850", "123", "2020")
    for invalid in ("850-123/2020", "850123/20", "850.123/2020 OR 1=1"):
        assert search.ANM_PROCESS_PATTERN.fullmatch(invalid) is None


def test_anm_service_failure_is_503_not_no_results(monkeypatch):
    def fail(*args, **kwargs):
        raise search.URLError("remote inaccessible")
    monkeypatch.setattr(search, "urlopen", fail)
    with pytest.raises(HTTPException) as exc:
        search.find_official_anm_process(process_number="850.123/2020")
    assert exc.value.status_code == 503


def test_anm_missing_custom_ca_fails_closed(monkeypatch):
    monkeypatch.setenv("ANM_CA_BUNDLE", "/nonexistent/anm-ca.pem")
    def unexpected(*args, **kwargs):
        raise AssertionError("Do not contact ANM when configured CA is missing")
    monkeypatch.setattr(search, "urlopen", unexpected)
    with pytest.raises(HTTPException) as exc:
        search.find_official_anm_process(process_number="858.027/2019")
    assert exc.value.status_code == 503
