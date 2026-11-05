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


def test_postgres_global_lock_denies_parallel_calls_before_sicar(monkeypatch):
    from contextlib import contextmanager
    class FakeConnection:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def scalar(self, *args, **kwargs): return False
        def commit(self): pass
    monkeypatch.setattr(pilot, "engine", SimpleNamespace(connect=lambda: FakeConnection()))
    class ForbiddenDB:
        def scalar(self, *args, **kwargs): pytest.fail("Database queried without global mutex")
    with pytest.raises(HTTPException) as exc:
        with pilot.reserve_platform_slot(
            ForbiddenDB(), user_id=uuid4(), car_code="AP-1600600-" + "A"*32
        ):
            pytest.fail("Remote operation started during another run")
    assert exc.value.status_code == 429


def test_pilot_records_a_failed_attempt_and_never_refunds_quota(monkeypatch):
    from app.models.rural_mapbiomas_pilot import RuralMapBiomasPilotRun
    class FakeConnection:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def scalar(self, *args, **kwargs): return True
        def commit(self): pass
        def execute(self, *args, **kwargs): return None
    monkeypatch.setattr(pilot, "engine", SimpleNamespace(connect=lambda: FakeConnection()))
    class FakeDB:
        def __init__(self):
            self.items = []
            self.commits = 0
            self.lookup_count = 0
        def scalar(self, *args):
            self.lookup_count += 1
            return None if self.lookup_count == 1 else 0
        def add(self, record): self.items.append(record)
        def commit(self): self.commits += 1
        def refresh(self, record): pass
        def rollback(self): pass
    db = FakeDB()
    with pytest.raises(RuntimeError, match="simulated failure"):
        with pilot.reserve_platform_slot(
            db, user_id=uuid4(), car_code="AP-1600600-" + "A"*32
        ) as record:
            assert record.status == "RESERVED"
            assert db.commits == 1
            raise RuntimeError("simulated failure")
    assert db.commits == 2
    assert isinstance(db.items[0], RuralMapBiomasPilotRun)
    assert db.items[0].status == "FAILED"
    assert db.items[0].error_category == "RuntimeError"
    assert db.items[0].finished_at is not None
    assert len(db.items[0].subject_hash) == 64


def test_pilot_one_attempt_per_user_day_blocks_before_reservation(monkeypatch):
    class FakeConnection:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def scalar(self, *args, **kwargs): return True
        def commit(self): pass
        def execute(self, *args, **kwargs): return None
    monkeypatch.setattr(pilot, "engine", SimpleNamespace(connect=lambda: FakeConnection()))
    class FakeDB:
        def scalar(self, *args): return uuid4()
        def add(self, *args): pytest.fail("Daily quota bypassed")
    with pytest.raises(HTTPException) as exc:
        with pilot.reserve_platform_slot(
            FakeDB(), user_id=uuid4(), car_code="AP-1600600-" + "A"*32
        ):
            pytest.fail("Quota bypassed")
    assert exc.value.status_code == 429
