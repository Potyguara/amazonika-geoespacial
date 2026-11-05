"""Offline checks of official IBAMA embargo ArcGIS REST intersection adapter."""
from copy import deepcopy

import pytest
from app.services import rural_ibama_embargos as ibama

SUBJECT = {
    "type": "Polygon",
    "coordinates": [[[-51.20, -0.20], [-51.10, -0.20], [-51.10, -0.10],
                     [-51.20, -0.10], [-51.20, -0.20]]],
}
INSIDE = {
    "type": "Polygon",
    "coordinates": [[[-51.19, -0.19], [-51.15, -0.19], [-51.15, -0.15],
                     [-51.19, -0.15], [-51.19, -0.19]]],
}
OUTSIDE = {
    "type": "Polygon",
    "coordinates": [[[-50.1, -0.2], [-50.05, -0.2], [-50.05, -0.15],
                     [-50.1, -0.15], [-50.1, -0.2]]],
}


def feature(code, geometry=INSIDE):
    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            "objectid": code, "num_tad": str(code), "num_processo": "00123/2026",
            "qtd_area_embargada": 80.5, "tipo_area": "Desmatamento",
            "cpf_cnpj_embargado": "DEVE SER OMITIDO",
            "nome_embargado": "DEVE SER OMITIDO",
        },
    }


def test_bounded_count_and_geometric_intersections(monkeypatch):
    calls = []
    def mock_query(params, **kwargs):
        calls.append(params)
        if params.get("returnCountOnly") == "true":
            return {"count": 2}
        return {"type": "FeatureCollection", "features": [feature(101), feature(102, OUTSIDE)]}
    monkeypatch.setattr(ibama, "_request_query", mock_query)
    report = ibama.embargo_preview(SUBJECT, include_geometry=True)
    assert report["status"] == "ANALYZED"
    assert report["program"] == "IBAMA EMBARGOS"
    assert report["candidate_features"] == 2
    assert report["interfering_features"] == 1
    assert report["overlap_hectares"] > 0
    assert 0 < report["overlap_percent"] < 100
    assert report["features"][0]["term"] == "101"
    assert report["features"][0]["declared_embargo_hectares"] == 80.5
    assert report["features"][0]["overlap_hectares"] != 80.5
    assert report["features"][0]["intersection_geometry"]["type"] == "Polygon"
    assert "cpf_cnpj_embargado" not in report["features"][0]["attributes"]
    assert "nome_embargado" not in report["features"][0]["attributes"]
    assert "geometry" in calls[0]
    assert calls[0]["where"] == "1=1"
    assert calls[1]["resultRecordCount"] == ibama.MAX_FEATURES
    assert calls[1]["f"] == "geojson"


def test_overlapping_embargos_use_unique_union_area(monkeypatch):
    def mock_query(params, **kwargs):
        if params.get("returnCountOnly") == "true":
            return {"count": 2}
        return {"type": "FeatureCollection", "features": [feature(101), feature(102)]}
    monkeypatch.setattr(ibama, "_request_query", mock_query)
    report = ibama.embargo_preview(SUBJECT)
    assert report["interfering_features"] == 2
    assert report["overlap_hectares"] == pytest.approx(
        report["features"][0]["overlap_hectares"], abs=0.001
    )


def test_no_records_is_valid_only_when_count_matches(monkeypatch):
    def mock_query(params, **kwargs):
        if params.get("returnCountOnly") == "true":
            return {"count": 0}
        return {"type": "FeatureCollection", "features": []}
    monkeypatch.setattr(ibama, "_request_query", mock_query)
    report = ibama.embargo_preview(SUBJECT)
    assert report["candidate_features"] == 0
    assert report["overlap_hectares"] == 0
    assert report["status"] == "ANALYZED"


def test_truncated_response_fails_closed(monkeypatch):
    def mock_query(params, **kwargs):
        if params.get("returnCountOnly") == "true":
            return {"count": 2}
        return {"type": "FeatureCollection", "features": [feature(101)]}
    monkeypatch.setattr(ibama, "_request_query", mock_query)
    with pytest.raises(ibama.IbamaEmbargoError, match="incompleta"):
        ibama.embargo_preview(SUBJECT)


def test_large_bbox_rejected_before_network(monkeypatch):
    monkeypatch.setattr(ibama, "_request_query",
                        lambda *args, **kwargs: pytest.fail("network unexpectedly called"))
    huge = {"type": "Polygon", "coordinates": [[
        [-53.0, -1.0], [-52.0, -1.0], [-52.0, 0.0],
        [-53.0, 0.0], [-53.0, -1.0],
    ]]}
    with pytest.raises(ValueError, match="excede"):
        ibama.embargo_preview(huge)


def test_unavailable_service_is_error_not_absence(monkeypatch):
    monkeypatch.setattr(ibama, "_request_query",
                        lambda *args, **kwargs: (_ for _ in ()).throw(
                            ibama.IbamaEmbargoError("indisponível")
                        ))
    with pytest.raises(ibama.IbamaEmbargoError, match="indisponível"):
        ibama.embargo_preview(SUBJECT)


def test_unvalidated_polygon_is_error(monkeypatch):
    def mock_query(params, **kwargs):
        if params.get("returnCountOnly") == "true":
            return {"count": 1}
        return {"type": "FeatureCollection", "features": [{
            "type": "Feature", "geometry": {"type": "Point", "coordinates": [-51.17, -0.17]},
            "properties": {"objectid": 123},
        }]}
    monkeypatch.setattr(ibama, "_request_query", mock_query)
    with pytest.raises(ibama.IbamaEmbargoError):
        ibama.embargo_preview(SUBJECT)


def test_arcgis_error_never_becomes_empty_result(monkeypatch):
    class MockResponse:
        headers = {"Content-Type": "application/json"}
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self, limit):
            return b'{"error":{"code":400,"message":"Invalid spatial query"}}'
    monkeypatch.setattr(ibama, "urlopen", lambda *args, **kwargs: MockResponse())
    with pytest.raises(ibama.IbamaEmbargoError, match="recusou"):
        ibama._request_query({"f": "geojson"})


def test_ibama_draft_pdf_with_real_polygon(monkeypatch):
    from datetime import datetime, timezone
    from app.services.rural_diagnostic_pdf import build_rural_monitoring_pdf
    def mock_query(params, **kwargs):
        if params.get("returnCountOnly") == "true":
            return {"count": 1}
        return {"type": "FeatureCollection", "features": [feature(100)]}
    monkeypatch.setattr(ibama, "_request_query", mock_query)
    result = ibama.embargo_preview(SUBJECT, include_geometry=True)
    pdf = build_rural_monitoring_pdf(
        property_name="Fazenda Teste", property_source="SIGEF",
        cadastral_code="BR-TESTE", subject_geometry=SUBJECT,
        monitoring=result, generated_at=datetime.now(timezone.utc),
    )
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 3000
