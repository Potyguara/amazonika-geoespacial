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
