"""Regression tests: preliminary PDF from server-side official monitoring results."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes import rural_diagnostics as routes
from app.services.rural_diagnostic_pdf import build_rural_monitoring_pdf, RuralIntersectionMap

SUBJECT = {"type": "Polygon", "coordinates": [[
    [-51.2, -0.2], [-51.1, -0.2], [-51.1, -0.1],
    [-51.2, -0.1], [-51.2, -0.2],
]]}
INTERSECTION = {"type": "Polygon", "coordinates": [[
    [-51.18, -0.18], [-51.14, -0.18], [-51.14, -0.14],
    [-51.18, -0.14], [-51.18, -0.18],
]]}


def monitoring():
    return {
        "status": "ANALYZED",
        "program": "PRODES",
        "layer": "prodes:exemplo",
        "layer_title": "Polígonos anuais (exemplo sintético)",
        "source": "INPE — TerraBrasilis",
        "service_url": "https://terrabrasilis.dpi.inpe.br/geoserver/ows",
        "queried_at": "2026-11-04T21:15:00Z",
        "method": "WFS BBOX e interseção exata",
        "warning": "Dados demonstrativos não representam infração.",
        "interfering_features": 1,
        "overlap_hectares": 19.5,
        "overlap_percent": 5.1,
        "features": [{
            "id": "PRODES-123",
            "overlap_hectares": 19.5,
            "attributes": {"year": "2025", "classe": "corte_raso"},
            "intersection_geometry": INTERSECTION,
        }],
    }


def test_preliminary_pdf_contains_pages_and_vector_map():
    pdf = build_rural_monitoring_pdf(
        property_name="Fazenda Teste",
        property_source="SIGEF — Brasil",
        cadastral_code="EXEMPLO-001",
        subject_geometry=SUBJECT,
        monitoring=monitoring(),
        generated_at=datetime(2026, 11, 4, 21, 15, tzinfo=timezone.utc),
    )
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 4000
    assert len(pdf) < 12 * 1024 * 1024


def test_map_flowable_can_render_geometry_collection():
    report = monitoring()
    report["features"][0]["intersection_geometry"] = {
        "type": "GeometryCollection", "geometries": [INTERSECTION],
    }
    rendered = build_rural_monitoring_pdf(
        property_name="Área de teste",
        property_source="PostGIS local",
        cadastral_code=None,
        subject_geometry=SUBJECT,
        monitoring=report,
        generated_at=datetime.now(timezone.utc),
    )
    assert rendered.startswith(b"%PDF")


def test_pdf_rejects_unverified_results():
    incomplete = monitoring()
    incomplete["status"] = "FAILED"
    with pytest.raises(ValueError, match="consulta incompleta"):
        build_rural_monitoring_pdf(
            property_name="Teste",
            property_source="WFS",
            cadastral_code=None,
            subject_geometry=SUBJECT,
            monitoring=incomplete,
            generated_at=datetime.now(timezone.utc),
        )


def test_route_revalidates_local_geometry_and_reexecutes_official_monitoring(monkeypatch):
    feature_id = uuid4()
    calls = {}
    def revalidate(uid, db):
        calls["local_id"] = uid
        return {"name": "Fazenda Teste", "source_name": "PostGIS",
                "geometry": SUBJECT, "feature_id": str(uid)}
    def get_monitoring(layer, geometry, *, include_geometry=False):
        calls["layer"] = layer
        calls["geometry"] = geometry
        calls["include_geometry"] = include_geometry
        return monitoring()
    monkeypatch.setattr(routes, "resolve_rural_perimeter", revalidate)
    monkeypatch.setattr(routes, "monitoring_preview", get_monitoring)
    payload = routes.RuralPreviewPdfRequest(
        retrieval="LOCAL_VECTOR", feature_id=str(feature_id),
        layer_name="prodes:exemplo",
    )
    response = routes.rural_preliminary_pdf(payload, db=object())
    assert response.media_type == "application/pdf"
    assert response.body.startswith(b"%PDF")
    assert response.headers["cache-control"] == "no-store"
    assert calls == {
        "local_id": feature_id,
        "layer": "prodes:exemplo",
        "geometry": SUBJECT,
        "include_geometry": True,
    }


def test_official_sigef_pdf_requires_coordinate():
    token = "a" * 64
    payload = routes.RuralPreviewPdfRequest(
        retrieval="OFFICIAL_WFS", feature_id=token,
        layer_name="prodes:exemplo",
    )
    with pytest.raises(HTTPException) as error:
        routes._resolve_pdf_subject(payload, db=object())
    assert error.value.status_code == 422


def test_official_car_pdf_requires_car_code():
    payload = routes.RuralPreviewPdfRequest(
        retrieval="OFFICIAL_CAR_WFS", feature_id="a" * 64,
        layer_name="prodes:exemplo",
    )
    with pytest.raises(HTTPException) as error:
        routes._resolve_pdf_subject(payload, db=object())
    assert error.value.status_code == 422
