"""Restricted pilot route/security tests; no database or external EE requests."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes import rural_diagnostics as routes
from app.services import rural_mapbiomas_pilot as pilot


def user(role):
    return SimpleNamespace(id=uuid4(), roles=[SimpleNamespace(code=role)])


def test_pilot_flag_fails_closed(monkeypatch):
    monkeypatch.setattr(pilot, "get_settings", lambda: SimpleNamespace(
        gee_internal_pilot_enabled=False, gee_enabled=True,
    ))
    with pytest.raises(HTTPException) as exc:
        pilot.verify_pilot_enabled()
    assert exc.value.status_code == 503


def test_pilot_is_inaccessible_to_analyst_without_gee_calls(monkeypatch):
    monkeypatch.setattr(routes, "build_restricted_mapbiomas_pdf",
                        lambda **kw: pytest.fail("GEE should never be called"))
    monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(
        gee_internal_pilot_enabled=True, gee_enabled=True,
    ))
    payload = routes.InternalMapBiomasPdfRequest(
        car_code="AP-1600600-" + "A" * 32,
    )
    with pytest.raises(HTTPException) as exc:
        routes.rural_internal_pilot_pdf(payload, db=object(), user=user("ANALISTA"))
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException):
        routes.rural_internal_pilot_status(user=user("ANALISTA"))


def test_pilot_disabled_even_for_admin_without_network(monkeypatch):
    monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(
        gee_internal_pilot_enabled=False, gee_enabled=True,
    ))
    monkeypatch.setattr(pilot, "get_settings", lambda: SimpleNamespace(
        gee_internal_pilot_enabled=False, gee_enabled=True,
    ))
    monkeypatch.setattr(routes, "build_restricted_mapbiomas_pdf",
                        lambda **kw: pytest.fail("GEE should never be called"))
    with pytest.raises(HTTPException) as exc:
        routes.rural_internal_pilot_pdf(
            routes.InternalMapBiomasPdfRequest(car_code="AP-1600600-" + "A" * 32),
            db=object(), user=user("ADMINISTRADOR"),
        )
    assert exc.value.status_code == 503


def test_pilot_admin_pdf_route_returns_private_document(monkeypatch):
    monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(
        gee_internal_pilot_enabled=True, gee_enabled=True,
    ))
    monkeypatch.setattr(routes, "verify_pilot_enabled", lambda: None)
    calls = {}
    def fake_builder(**kw):
        calls.update(kw)
        return b"%PDF-test"
    monkeypatch.setattr(routes, "build_restricted_mapbiomas_pdf", fake_builder)
    admin = user("ADMINISTRADOR")
    payload = routes.InternalMapBiomasPdfRequest(
        car_code="AP-1600600-" + "A" * 32,
    )
    response = routes.rural_internal_pilot_pdf(payload, db="db", user=admin)
    assert response.body == b"%PDF-test"
    assert calls == {"db":"db","user_id":admin.id,"car_code":payload.car_code}
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["x-report-type"] == "preliminary-rural-mapbiomas-internal"


def test_pilot_accepts_only_collection_11_verified_year():
    with pytest.raises(Exception):
        routes.InternalMapBiomasPdfRequest(
            car_code="AP-1600600-" + "A" * 32, year=2024,
        )


def test_quota_limits_and_year_are_conservative():
    assert pilot.MAX_AREA_HA == 1200
    assert pilot.MAX_REMOTE_PIXELS == 30000
    assert pilot.MAX_PLATFORM_ATTEMPTS_DAY <= 5
