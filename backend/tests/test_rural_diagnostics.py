"""Rural diagnosis: location never invents a boundary from one coordinate."""
from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes.rural_diagnostics import (
    MAX_CANDIDATES,
    locate_rural_property,
    resolve_rural_perimeter,
    validate_coordinate,
)


class FakeResult:
    def __init__(self, records):
        self.records = records

    def mappings(self):
        return self

    def all(self):
        return self.records

    def first(self):
        return self.records[0] if self.records else None


class FakeDb:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, statement, parameters):
        self.calls.append((str(statement), parameters))
        return FakeResult(self.rows)


def record():
    return {
        "feature_id": uuid4(),
        "source_id": uuid4(),
        "source_slug": "incra-sigef-brasil",
        "source_name": "SIGEF — Brasil",
        "institution": "INCRA",
        "external_id": "PARCEL-001",
        "feature_name": "Fazenda referência",
        "properties": {"parcela_codigo": "BR-001"},
        "reference_date": date(2026, 9, 1),
        "imported_at": datetime.now(timezone.utc),
        "vertex_count": 15,
        "area_hectares": 125.5,
    }


def test_coordinate_validation():
    assert validate_coordinate(0.01, -51.05) == (0.01, -51.05)
    for invalid in [(91, -51), (0, 181), (float("nan"), -51)]:
        with pytest.raises(ValueError):
            validate_coordinate(*invalid)


def test_point_without_registered_perimeter_is_not_reported_as_no_property():
    result = locate_rural_property(0.01, -51.05, FakeDb([]))
    assert result["point_only"] is True
    assert result["candidate_count"] == 0
    assert result["coverage"].startswith("Apenas perímetros")


def test_query_is_spatial_indexed_and_requires_current_cadastral_version():
    db = FakeDb([record()])
    result = locate_rural_property(0.01, -51.05, db)
    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert candidate["cadastral_code"] == "BR-001"
    assert candidate["reference_date"] == "2026-09-01"
    sql, params = db.calls[0]
    assert "ST_Covers" in sql
    assert "f.geom && p.geom" in sql
    assert "v.is_current IS TRUE" in sql
    assert params["limit"] == MAX_CANDIDATES + 1
    assert params["longitude"] == -51.05


def test_does_not_silently_discard_ambiguous_candidates():
    result = locate_rural_property(0.01, -51.05, FakeDb([record() for _ in range(MAX_CANDIDATES + 1)]))
    assert result["has_more"] is True
    assert len(result["candidates"]) == MAX_CANDIDATES


def test_full_geometry_for_selected_existing_candidate():
    row = {
        "feature_id": uuid4(),
        "name": "Fazenda Teste",
        "external_id": "BR-02",
        "source_name": "SIGEF — Brasil",
        "source_slug": "incra-sigef-brasil",
        "reference_date": date(2026, 9, 1),
        "vertex_count": 4,
        "geometry": '{"type":"Polygon","coordinates":[[[-51,0],[-50,0],[-50,1],[-51,0]]]}',
    }
    db = FakeDb([row])
    result = resolve_rural_perimeter(row["feature_id"], db)
    assert result["geometry"]["type"] == "Polygon"
    assert result["name"] == "Fazenda Teste"
    sql, params = db.calls[0]
    assert "ST_NPoints(f.geom) <= :max_vertices" in sql
    assert params["feature_id"] == row["feature_id"]


def test_geometry_cannot_be_resolved_from_missing_identifier():
    with pytest.raises(HTTPException) as error:
        resolve_rural_perimeter(uuid4(), FakeDb([]))
    assert error.value.status_code == 404


def test_refuses_non_polygon_even_with_valid_geospatial_record():
    db = FakeDb([{
        "feature_id": uuid4(), "name": "Não é imóvel",
        "external_id": None, "source_name": "Fonte",
        "source_slug": "incra-sigef-brasil",
        "reference_date": None,
        "geometry": '{"type":"Point","coordinates":[-51,0]}',
    }])
    with pytest.raises(HTTPException) as error:
        resolve_rural_perimeter(uuid4(), db)
    assert error.value.status_code == 422
