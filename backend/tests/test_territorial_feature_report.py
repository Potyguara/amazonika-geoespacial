"""Regression tests for individual territorial-feature PDF reporting."""
from uuid import uuid4

from PIL import Image, ImageDraw

from app.services.territorial_report import (
    _draw_geometry,
    _intersecting_features,
)


def _triangle(x):
    return {
        "type": "Polygon",
        "coordinates": [[[x, 0], [x + 10, 0], [x, 10], [x, 0]]],
    }


def test_map_renderer_draws_geometry_collection_from_postgis():
    image = Image.new("RGB", (120, 120), "white")
    draw = ImageDraw.Draw(image, "RGBA")
    geometry = {
        "type": "GeometryCollection",
        "geometries": [_triangle(5), _triangle(35)],
    }
    _draw_geometry(draw, geometry, lambda p: (int(p[0]), int(p[1])),
                   outline="#c02c35", fill="#ed677680", width=3)
    assert image.getpixel((6, 6)) != (255, 255, 255)
    assert image.getpixel((36, 6)) != (255, 255, 255)


def test_individual_features_preserve_ids_area_attributes_and_geometry():
    item = {
        "id": uuid4(),
        "external_id": "parcela-1",
        "name": "Fazenda teste",
        "properties": {
            "parcela_codigo": "INCRA-01",
            "area_hectares": 20.0,
            "classe_ambiental": "Tipo A",
            "cpf": "DO_NOT_INCLUDE",
        },
        "geometry": '{"type":"Polygon","coordinates":[[[0,0],[1,0],[0,1],[0,0]]]}',
        "intersection": '{"type":"Polygon","coordinates":[[[0,0],[0.5,0],[0,0.5],[0,0]]]}',
        "overlap_ha": 2.50771,
    }

    class FakeResult:
        def mappings(self):
            return self

        def all(self):
            return [item]

    class FakeDB:
        def execute(self, *args, **kwargs):
            return FakeResult()

    rows = _intersecting_features(FakeDB(), uuid4(), uuid4())
    assert len(rows) == 1
    assert rows[0]["external_id"] == "parcela-1"
    assert rows[0]["attributes"]["parcela_codigo"] == "INCRA-01"
    assert rows[0]["attributes"]["classe_ambiental"] == "Tipo A"
    assert "cpf" not in rows[0]["attributes"]
    assert rows[0]["overlap_hectares"] == 2.50771
    assert rows[0]["geometry"]["type"] == "Polygon"
    assert rows[0]["intersection_geometry"]["type"] == "Polygon"


def test_refuse_truncated_feature_detail():
    item = {
        "id": uuid4(), "external_id": "1", "name": "",
        "properties": {},
        "geometry": '{"type":"Point","coordinates":[0,0]}',
        "intersection": '{"type":"Point","coordinates":[0,0]}',
        "overlap_ha": 0,
    }

    class FakeResult:
        def mappings(self):
            return self

        def all(self):
            return [item, item]

    class FakeDB:
        def execute(self, *args, **kwargs):
            return FakeResult()

    import pytest
    with pytest.raises(ValueError, match="Divida a área"):
        _intersecting_features(FakeDB(), uuid4(), uuid4(), limit=1)


def test_map_export_contains_individual_parcel_outlines_and_overlaps(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from app.services import territorial_report as report

    subject = {
        "type": "Polygon",
        "coordinates": [[[-51.05, -0.1], [-51.01, -0.1], [-51.01, -0.06],
                         [-51.05, -0.06], [-51.05, -0.1]]],
    }
    west = {
        "type": "Polygon",
        "coordinates": [[[-51.08, -0.12], [-51.03, -0.12], [-51.03, -0.07],
                         [-51.08, -0.07], [-51.08, -0.12]]],
    }
    east = {
        "type": "Polygon",
        "coordinates": [[[-51.025, -0.09], [-50.99, -0.09], [-50.99, -0.04],
                         [-51.025, -0.04], [-51.025, -0.09]]],
    }
    from shapely.geometry import shape, mapping
    geometry_parts = [west, east]
    clipped = [mapping(shape(g).intersection(shape(subject)))
               for g in geometry_parts]
    monkeypatch.setattr(report, "_subject_geojson", lambda *args: subject)
    monkeypatch.setattr(report, "_context_extent_geojson", lambda *args: subject)
    monkeypatch.setattr(report, "_context_geojson",
                        lambda *args: ({"type": "GeometryCollection",
                                       "geometries": geometry_parts}, 2))
    monkeypatch.setattr(report, "_overlap_geojson",
                        lambda *args: {"type": "GeometryCollection",
                                       "geometries": clipped})
    analysis = SimpleNamespace(id=uuid4(), created_at=datetime.now(timezone.utc))
    snapshot = {
        "area_hectares": 100, "tracking_code": "TESTE-RELATORIO",
        "results": [{
            "source_name": "SIGEF Brasil", "institution": "INCRA",
            "source_version_id": str(uuid4()), "intersects": True,
            "features": [
                {"index": n+1, "name": f"Parcela {n+1}", "geometry": g,
                 "intersection_geometry": overlap}
                for n, (g, overlap) in enumerate(zip(geometry_parts, clipped))
            ],
        }],
    }
    target = tmp_path / "mapa.png"
    report.build_analysis_map(None, analysis, snapshot, target)
    assert target.exists()
    with Image.open(target) as image:
        assert image.size == (1600, 1050)
        pixels = list(image.crop((60, 140, 1540, 780)).getdata())
        reddish = sum(1 for r, g, b in pixels if r > 120 and r > g * 1.35 and r > b * 1.1)
        assert reddish > 100


def test_pdf_smoke_renders_individual_feature_table(tmp_path):
    from datetime import datetime, timezone
    from app.services.territorial_report import build_report_pdf

    now = datetime.now(timezone.utc).isoformat()
    picture = tmp_path / "map.png"
    Image.new("RGB", (1600, 1050), "white").save(picture)
    snapshot = {
        "tracking_code": "TESTE-PARCELAS",
        "analysis_name": "Teste com duas parcelas",
        "system": "Amazonika Geoespacial",
        "area_hectares": 100.0,
        "geometry_kind": "POLYGON",
        "perimeter_meters": 4000.0,
        "analysis_created_at": now,
        "issued_at": now,
        "executor": {"name": "Responsável Técnico"},
        "issuer": {"name": "Responsável Técnico"},
        "warnings": [],
        "source_statuses": [],
        "results": [{
            "source_id": str(uuid4()),
            "source_name": "SIGEF — Brasil",
            "institution": "INCRA",
            "source_version_id": str(uuid4()),
            "intersects": True,
            "matched_features": 2,
            "overlap_hectares": 22.5,
            "overlap_percent": 22.5,
            "nearest_distance_meters": 0.0,
            "reference_date": None,
            "features": [{
                "index": i,
                "external_id": f"SIGEF-PARCELA-{i}",
                "name": f"Parcela {i}",
                "attributes": {"parcela_codigo": f"COD-{i}", "status": "TITULACAO"},
                "overlap_hectares": 10.0 + i,
                "geometry": _triangle(0),
                "intersection_geometry": _triangle(0),
            } for i in (1, 2)],
        }],
    }
    pdf = tmp_path / "report.pdf"
    build_report_pdf(snapshot, picture, pdf, "https://geo.amazonikaengenharia.com.br/test")
    assert pdf.exists()
    assert pdf.read_bytes().startswith(b"%PDF")
    assert pdf.stat().st_size > 5000
