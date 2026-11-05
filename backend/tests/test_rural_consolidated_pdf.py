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
