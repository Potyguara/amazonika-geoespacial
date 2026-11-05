"""HTTP + real PostgreSQL integration for the restricted rural cartographic pilot.

OPT-IN ONLY: requires an isolated disposable PostgreSQL database and
AMAZONIKA_TEST_PG_INTEGRATION=yes. No external CAR or GEE calls; mocked output.
Never run against the production DB.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

pytestmark = pytest.mark.skipif(
    os.environ.get("AMAZONIKA_TEST_PG_INTEGRATION") != "yes",
    reason="Dedicated disposable PostgreSQL test environment not selected",
)


def test_admin_http_audited_once_in_disposable_postgres(monkeypatch):
    url = os.environ.get("DATABASE_URL", "")
    # A strong fail-closed guard against accidentally invoking this on production.
    if "amazonika_pilot_test" not in url or "pilot-postgres:" not in url:
        pytest.fail("Database must be the isolated pilot-postgres/amazonika_pilot_test")

    from app.main import app
    from app.db.session import engine
    from app.models.auth import User
    from app.models.rural_mapbiomas_pilot import RuralMapBiomasPilotRun
    from app.api.routes import rural_diagnostics as routes
    from app.services.auth import get_current_session
    from app.services import rural_mapbiomas_pilot as pilot
    from app.services.rural_mapbiomas_cartography import ThematicThumbnail
    from app.services.rural_mapbiomas import _normalize_statistics
    from sqlalchemy.orm import Session

    assert engine.url.database == "amazonika_pilot_test"
    User.__table__.create(engine, checkfirst=True)
    RuralMapBiomasPilotRun.__table__.create(engine, checkfirst=True)

    sample_id = uuid4()
    with Session(engine) as db:
        db.add(User(
            id=sample_id,
            email="pilot-admin@example.invalid",
            full_name="Admin de teste",
            password_hash="not-a-real-password",
            is_active=True,
        ))
        db.commit()

    fake_permissions = [SimpleNamespace(code=x) for x in (
        "analysis.view", "analysis.execute", "analysis.export",
    )]
    admin = SimpleNamespace(
        id=sample_id,
        roles=[SimpleNamespace(code="ADMINISTRADOR", permissions=fake_permissions)],
    )
    analyst = SimpleNamespace(
        id=sample_id,
        roles=[SimpleNamespace(code="ANALISTA", permissions=fake_permissions)],
    )
    principal = {"current": admin}
    app.dependency_overrides[get_current_session] = (
        lambda: SimpleNamespace(user=principal["current"])
    )
    monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(
        gee_internal_pilot_enabled=True, gee_enabled=True,
    ))
    monkeypatch.setattr(pilot, "get_settings", lambda: SimpleNamespace(
        gee_internal_pilot_enabled=True, gee_enabled=True,
    ))
    geom = {"type": "Polygon", "coordinates": [[
        [-51.2, .02], [-51.199, .02],
        [-51.199, .021], [-51.2, .021], [-51.2, .02],
    ]]}
    calls = []
    monkeypatch.setattr(pilot, "fetch_car_candidate", lambda code: (
        calls.append("sicar") or {"feature_id": "a" * 64}
    ))
    monkeypatch.setattr(pilot, "resolve_car_candidate", lambda *args: {
        "geometry": geom, "name": "Imóvel teste", "source_name": "SICAR",
    })
    monkeypatch.setattr(pilot, "_initialize_gee", lambda: object())
    monkeypatch.setattr(pilot, "_reduce_class_areas", lambda *args, **kwargs: (
        calls.append("reduction") or {"groups": [{"class": 11, "sum": 1}]}
    ))
    monkeypatch.setattr(pilot, "fetch_mapbiomas_thematic_thumbnail", lambda *args, **kwargs: (
        calls.append("thumbnail") or ThematicThumbnail(
            png=b"fake-png-only-used-by-mocked-PDF",
            bounds=(-51.2, .02, -51.199, .021),
            width=10, height=10, year=2025, class_codes=(11,),
        )
    ))
    monkeypatch.setattr(pilot, "mapbiomas_pdf", lambda **kwargs: (
        calls.append("pdf") or b"%PDF-test-integration"
    ))

    endpoint = "/api/v1/rural-diagnostics/mapbiomas/internal-pilot/pdf"
    payload = {"car_code": "AP-1600600-" + "A"*32, "year": 2025}
    try:
        client = TestClient(app)
        if True:
            principal["current"] = analyst
            unauthorized = client.post(endpoint, json=payload)
            assert unauthorized.status_code == 403
            assert calls == []

            principal["current"] = admin
            first = client.post(endpoint, json=payload)
            assert first.status_code == 200, first.text[:300]
            assert first.headers["content-type"] == "application/pdf"
            assert first.headers["cache-control"] == "no-store, private"
            assert first.content.startswith(b"%PDF")
            assert calls == ["sicar", "reduction", "thumbnail", "pdf"]

            duplicate = client.post(endpoint, json=payload)
            assert duplicate.status_code == 429
            assert calls == ["sicar", "reduction", "thumbnail", "pdf"]
        with Session(engine) as db:
            records = db.scalars(
                select(RuralMapBiomasPilotRun).where(
                    RuralMapBiomasPilotRun.user_id == sample_id
                )
            ).all()
            assert len(records) == 1
            assert records[0].status == "COMPLETED"
            assert records[0].pdf_bytes == len(b"%PDF-test-integration")
            assert records[0].subject_hash != payload["car_code"]
            assert records[0].quota_day == datetime.now(timezone.utc).date()
    finally:
        app.dependency_overrides.pop(get_current_session, None)
