"""Real PostgreSQL/PostGIS + private PDF integration for consolidated jobs.

Requires a DEDICATED, disposable container named consolidated-postgres.
No production or homologation database is accepted. Official services are
mocked, Google GEE is not invoked. Opt-in environment:
AMAZONIKA_TEST_CONSOLIDATED_PG=yes.
"""
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from geoalchemy2.shape import from_shape
from shapely.geometry import Polygon
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.environ.get("AMAZONIKA_TEST_CONSOLIDATED_PG") != "yes",
    reason="Needs disposable consolidated-postgres/PostGIS instance",
)


def test_full_consolidated_job_isolated_pg_and_private_pdf(monkeypatch, tmp_path):
    from app.db.session import engine
    from app.db.base import Base
    import app.models
    from app.models.auth import User
    from app.models.analysis import Analysis
    from app.models.rural_consolidated import RuralConsolidatedJob
    from app.api.routes import rural_consolidated as api
    from app.services import rural_consolidated as svc
    from fastapi import BackgroundTasks, HTTPException

    if not (
        os.getenv("AMAZONIKA_TEST_CONSOLIDATED_PG") == "yes"
        and engine.url.host == "consolidated-postgres"
        and engine.url.database == "amazonika_consolidated_test"
        and engine.url.username == "consolidated"
    ):
        pytest.fail("Integration blocked: wrong database/host/user")

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(bind=engine)

    id_owner, id_other = uuid4(), uuid4()
    admin = SimpleNamespace(
        id=id_owner, roles=[SimpleNamespace(code="ADMINISTRADOR")]
    )
    outsider = SimpleNamespace(id=id_other, roles=[])

    monkeypatch.setattr(
        svc, "embargo_preview", lambda geometry: {
            "status": "ANALYZED", "source": "IBAMA — teste mockado",
            "layer": "embargos", "queried_at": "2026-11-05T23:00:00Z",
            "interfering_features": 0, "overlap_hectares": 0,
            "overlap_percent": 0, "features": [],
            "method": "Interseção de teste", "warning": "Resultado simulado.",
        },
    )
    # No monitoring selection: no INPE requests and no paid Google calls.
    monkeypatch.setattr(
        svc, "monitoring_preview",
        lambda *_args, **_kwargs: pytest.fail("Monitoring call without selected layer"),
    )
    monkeypatch.setattr(
        svc, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path)
    )
    monkeypatch.setattr(
        api, "get_settings", lambda: SimpleNamespace(storage_dir=tmp_path)
    )

    fake_user = User(
        id=id_owner, email=f"consolidated-{id_owner.hex}@example.com",
        full_name="Teste consolidado", password_hash="nonlogin-test",
        is_active=True,
    )
    geom = Polygon([
        (-51.100, 0.01), (-51.098, 0.01),
        (-51.098, 0.012), (-51.100, 0.012), (-51.100, 0.01),
    ])
    analysis_id = uuid4()
    with Session(engine) as db:
        db.add(fake_user)
        db.flush()
        db.add(Analysis(
            id=analysis_id, name="Imóvel homologação de teste",
            status="COMPLETED", geometry_kind="POLYGON",
            input_geom=from_shape(geom, srid=4674),
            area_hectares=4.9201,
            created_by_user_id=id_owner,
            warnings_json=[], source_status_json=[], subject_json={},
        ))
        db.commit()

    with Session(engine) as db:
        tasks = BackgroundTasks()
        accepted = api.create_consolidated_report(
            analysis_id=analysis_id, tasks=tasks,
            options=None, db=db, user=admin,
        )
        assert accepted["status"] == "QUEUED"
        assert accepted["report_stage"] == "PRELIMINARY_PARTIAL"
        job_id = accepted["job_id"]

    svc.run_consolidated_job(__import__("uuid").UUID(job_id))
    with Session(engine) as db:
        status = api.consolidated_job_status(
            __import__("uuid").UUID(job_id), db=db, user=admin,
        )
        assert status["status"] == "COMPLETED", status
        assert status["progress_percent"] == 100
        assert status["pdf_ready"] is True
        sections = {item["code"]: item for item in status["sections"]}
        assert sections["ENVIRONMENTAL_ENFORCEMENT"]["status"] == "NO_OCCURRENCE"
        assert sections["LAND_COVER_MAPBIOMAS"]["status"] == "NOT_RUN"
        assert sections["PRODES_DETER"]["status"] == "NOT_RUN"
        assert sections["TERRITORIAL_OVERLAYS"]["status"] == "NOT_RUN"

        response = api.download_consolidated_pdf(
            __import__("uuid").UUID(job_id), db=db, user=admin,
        )
        pdf = Path(response.path).read_bytes()
        assert pdf.startswith(b"%PDF") and len(pdf) > 3000
        assert hashlib.sha256(pdf).hexdigest() == response.headers["x-report-sha256"]
        assert response.headers["x-report-type"] == "full-farm-consolidated-preliminary-partial"

        with pytest.raises(HTTPException) as exc:
            api.download_consolidated_pdf(
                __import__("uuid").UUID(job_id), db=db, user=outsider,
            )
        assert exc.value.status_code == 404

        job = db.get(RuralConsolidatedJob, __import__("uuid").UUID(job_id))
        assert job.snapshot_json["territorial_evidence"]["analyzed_count"] == 0
        assert job.snapshot_json["ibama_embargos"]["count"] == 0
        assert job.snapshot_json["ibama_embargos"]["source"] == "IBAMA — teste mockado"
        assert next(section for section in job.snapshot_json["sections"]
                    if section["code"] == "ENVIRONMENTAL_ENFORCEMENT")["status"] == "NO_OCCURRENCE"
        assert job.report_type == "FULL_FARM_CONSOLIDATED"

    # DB and generated files are disposable by the calling test environment.
