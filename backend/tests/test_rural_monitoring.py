"""Offline tests for the public TerraBrasilis PRODES/DETER adapter."""
import json
from xml.etree import ElementTree as ET

import pytest

from app.services import rural_monitoring as monitor


CAPABILITIES = b"""<?xml version="1.0"?>
<WFS_Capabilities>
  <FeatureTypeList>
    <FeatureType>
      <Name>deter-amz:deter_public</Name>
      <Title>DETER public alerts Amazonia</Title>
    </FeatureType>
    <FeatureType>
      <Name>prodes-amz:prodes_public</Name>
      <Title>PRODES annual polygons</Title>
    </FeatureType>
    <FeatureType>
      <Name>unrelated:admin</Name>
      <Title>Administrative boundaries</Title>
    </FeatureType>
  </FeatureTypeList>
</WFS_Capabilities>"""

SUBJECT = {
    "type": "Polygon",
    "coordinates": [[
        [-51.20, -0.20], [-51.10, -0.20],
        [-51.10, -0.10], [-51.20, -0.10],
        [-51.20, -0.20],
    ]],
}


def record(name, geometry):
    return {"type": "Feature", "id": name, "properties": {"year": 2025},
            "geometry": geometry}


def setup_catalogue(monkeypatch):
    monitor._catalog_snapshot.cache_clear()
    monkeypatch.setattr(monitor, "_CATALOG_VALID_UNTIL", 0.0)
    monkeypatch.setattr(
        monitor, "_request",
        lambda params, max_bytes, timeout=25: CAPABILITIES
    )
    return monitor.monitoring_catalog()


def test_only_prodes_and_deter_layers_from_capabilities(monkeypatch):
    catalogue = setup_catalogue(monkeypatch)
    assert sorted(item["program"] for item in catalogue["layers"]) == ["DETER", "PRODES"]
    assert len(catalogue["layers"]) == 2


def test_rejects_layer_outside_verified_catalogue(monkeypatch):
    setup_catalogue(monkeypatch)
    with pytest.raises(ValueError, match="não consta"):
        monitor.monitoring_preview("unrelated:admin", SUBJECT)


def test_exact_clipped_intersection_and_no_national_download(monkeypatch):
    setup_catalogue(monkeypatch)
    within = {
        "type": "Polygon",
        "coordinates": [[
            [-51.18, -0.18], [-51.12, -0.18],
            [-51.12, -0.12], [-51.18, -0.12],
            [-51.18, -0.18],
        ]],
    }
    outside = {
        "type": "Polygon",
        "coordinates": [[
            [-52.0, -1.0], [-51.9, -1.0],
            [-51.9, -0.9], [-52.0, -0.9],
            [-52.0, -1.0],
        ]],
    }
    queries = []

    def mock_request(params, max_bytes, timeout=25):
        queries.append(params)
        return json.dumps({"type": "FeatureCollection", "features": [
            record("in", within), record("out", outside),
        ]}).encode()

    monkeypatch.setattr(monitor, "_request", mock_request)
    report = monitor.monitoring_preview("prodes-amz:prodes_public", SUBJECT)
    assert report["program"] == "PRODES"
    assert report["interfering_features"] == 1
    assert report["overlap_hectares"] > 0
    assert 0 < report["overlap_percent"] < 100
    assert queries[0]["maxFeatures"] == str(monitor.MAX_FEATURES)
    assert queries[0]["typeName"] == "prodes-amz:prodes_public"
    assert "bbox" in queries[0]
    assert "CQL_FILTER" not in queries[0]


def test_rejects_too_large_subject(monkeypatch):
    setup_catalogue(monkeypatch)
    too_large = {
        "type": "Polygon",
        "coordinates": [[
            [-52, -1], [-51, -1], [-51, 0], [-52, 0], [-52, -1],
        ]],
    }
    with pytest.raises(ValueError, match="excede"):
        monitor.monitoring_preview("deter-amz:deter_public", too_large)


def test_refuses_truncated_wfs_features(monkeypatch):
    setup_catalogue(monkeypatch)
    def large_reply(*args, **kwargs):
        return json.dumps({
            "type": "FeatureCollection",
            "features": [record("test", SUBJECT)] * monitor.MAX_FEATURES,
        }).encode()
    monkeypatch.setattr(monitor, "_request", large_reply)
    with pytest.raises(monitor.MonitoringQueryError, match="limite"):
        monitor.monitoring_preview("deter-amz:deter_public", SUBJECT)


def test_ogc_exception_not_mistaken_for_absence_of_desmatamento():
    xml = b"<ServiceExceptionReport><ServiceException>Layer unavailable</ServiceException></ServiceExceptionReport>"
    with pytest.raises(monitor.MonitoringQueryError, match="Layer unavailable"):
        monitor._parse_xml(xml)


def test_invalid_geometry_rejected():
    with pytest.raises(ValueError):
        monitor.validate_subject({"type": "Point", "coordinates": [-51.1, -0.1]})
