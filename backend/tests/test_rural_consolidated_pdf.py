"""Offline regression for the separate preliminary consolidated renderer.

No external WFS, Earth Engine, Google Maps, or database.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
import hashlib

from app.services.rural_consolidated import build_job_snapshot, render_preliminary_consolidated_pdf, THEMES


class FakeResults:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, rows):
        self.rows = rows

    def scalar(self, query, params=None):
        # The SELECT is ST_AsGeoJSON on the frozen Analysis geometry.
        return '{"type":"Polygon","coordinates":[[[-51,0],[-50.99,0],[-50.99,0.01],[-51,0.01],[-51,0]]]}'

    def execute(self, query, params=None):
        return FakeResults(self.rows)


def _analysis(statuses=None):
    return SimpleNamespace(
        id=uuid4(), name="Gleba de homologação", geometry_kind="POLYGON",
        status="COMPLETED", area_hectares=186.6908,
        subject_json={}, source_status_json=statuses or [],
    )


def test_unchanged_territorial_zeros_do_not_become_clean_farm():
    snap = build_job_snapshot(FakeSession([]), _analysis())
    overlay = next(x for x in snap["sections"] if x["code"] == "TERRITORIAL_OVERLAYS")
    mapbiomas = next(x for x in snap["sections"] if x["code"] == "LAND_COVER_MAPBIOMAS")
    assert overlay["status"] == "NOT_RUN"
    assert mapbiomas["status"] == "NOT_RUN"
    assert snap["territorial_evidence"]["analyzed_count"] == 0
    assert snap["report_stage"] == "PRELIMINARY_PARTIAL"
    assert len(snap["sections"]) == len(THEMES)


def test_source_failure_does_not_allow_false_negative():
    statuses = [{
        "source_id": str(uuid4()), "source_name": "Fonte indisponível",
        "institution": "Órgão", "status": "FAILED",
        "matched_features": None,
    }]
    snap = build_job_snapshot(FakeSession([]), _analysis(statuses))
    overlay = next(x for x in snap["sections"] if x["code"] == "TERRITORIAL_OVERLAYS")
    assert overlay["status"] == "UNAVAILABLE"
    assert snap["territorial_evidence"]["inconclusive_count"] == 1


def test_valid_pdf_contains_bytes_and_is_deterministically_hashable():
    snap = build_job_snapshot(FakeSession([]), _analysis())
    document = render_preliminary_consolidated_pdf(snap)
    assert document.startswith(b"%PDF")
    assert len(document) > 3500
    assert len(hashlib.sha256(document).hexdigest()) == 64


def test_ibama_real_theme_populates_only_with_verified_source(monkeypatch):
    from app.services import rural_consolidated as svc
    snap = build_job_snapshot(FakeSession([]), _analysis())
    monkeypatch.setattr(svc, "embargo_preview", lambda geom: {
        "status": "ANALYZED",
        "source": "IBAMA PAMGIA", "layer": "Embargos",
        "queried_at": "2026-11-05T20:00:00+00:00",
        "interfering_features": 1, "overlap_hectares": 1.25,
        "overlap_percent": 0.67, "method": "Interseção",
        "warning": "Não prova responsabilidade",
        "features": [{"term": "EMB-TESTE", "process": "PROT-TESTE",
                       "overlap_hectares": 1.25}],
    })
    svc.analyze_ibama_embargos(snap, {"type": "Polygon", "coordinates": []})
    section = next(x for x in snap["sections"]
                   if x["code"] == "ENVIRONMENTAL_ENFORCEMENT")
    assert section["status"] == "COMPLETE"
    assert snap["ibama_embargos"]["count"] == 1
    assert svc.render_preliminary_consolidated_pdf(snap).startswith(b"%PDF")


def test_ibama_service_failure_is_not_no_occurrence(monkeypatch):
    from app.services import rural_consolidated as svc
    snap = build_job_snapshot(FakeSession([]), _analysis())
    def fails(_):
        raise svc.IbamaEmbargoError("Serviço indisponível")
    monkeypatch.setattr(svc, "embargo_preview", fails)
    svc.analyze_ibama_embargos(snap, {})
    section = next(x for x in snap["sections"]
                   if x["code"] == "ENVIRONMENTAL_ENFORCEMENT")
    assert section["status"] == "UNAVAILABLE"
    assert snap["ibama_embargos"]["status"] == "UNAVAILABLE"


def test_monitoring_requires_explicit_layer(monkeypatch):
    from app.services import rural_consolidated as svc
    snap = build_job_snapshot(FakeSession([]), _analysis())
    monkeypatch.setattr(svc, "monitoring_preview", lambda *_args: (_ for _ in ()).throw(
        AssertionError("Unexpected monitoring call")
    ))
    svc.analyze_monitoring(snap, {}, None)
    assert snap.get("monitoring_result") is None
    section = next(x for x in snap["sections"] if x["code"] == "PRODES_DETER")
    assert section["status"] == "NOT_RUN"


def test_monitoring_independent_real_result(monkeypatch):
    from app.services import rural_consolidated as svc
    snap = build_job_snapshot(FakeSession([]), _analysis())
    monkeypatch.setattr(svc, "monitoring_preview", lambda layer, geometry: {
        "status": "ANALYZED", "layer": layer, "layer_title": "PRODES Teste",
        "source": "INPE", "program": "PRODES",
        "queried_at": "2026-11-05T20:00:00+00:00",
        "interfering_features": 1, "overlap_hectares": 0.8,
        "method": "WFS", "warning": "Indicador remoto",
        "features": [{"id": "test-feature", "overlap_hectares": 0.8}],
    })
    svc.analyze_monitoring(snap, {}, "testing:prodes")
    section = next(x for x in snap["sections"] if x["code"] == "PRODES_DETER")
    assert section["status"] == "COMPLETE"
    assert snap["monitoring_result"]["count"] == 1
    assert svc.render_preliminary_consolidated_pdf(snap).startswith(b"%PDF")


def test_monitoring_failure_is_not_clean_report(monkeypatch):
    from app.services import rural_consolidated as svc
    snap = build_job_snapshot(FakeSession([]), _analysis())
    def fails(*_args):
        raise svc.MonitoringQueryError("Upstream unavailable")
    monkeypatch.setattr(svc, "monitoring_preview", fails)
    svc.analyze_monitoring(snap, {}, "testing:prodes")
    section = next(x for x in snap["sections"] if x["code"] == "PRODES_DETER")
    assert section["status"] == "UNAVAILABLE"
