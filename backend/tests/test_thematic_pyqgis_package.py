"""Integration regression: GeoPackage attributes -> PyQGIS request, without network.

Run from backend: python -m pytest tests/test_thematic_pyqgis_package.py -q
"""
import json
from types import SimpleNamespace
from unittest.mock import patch

import geopandas as gpd
from shapely.geometry import Polygon, box

from app.services.thematic_pyqgis_package import render_package_pyqgis


def test_real_gpkg_preserves_categorical_attributes(tmp_path):
    gpkg = tmp_path / "uso_solo.gpkg"
    polygons = [
        Polygon([(-51.15,-0.12),(-51.14,-0.12),(-51.14,-0.11),(-51.15,-0.11)]),
        Polygon([(-51.14,-0.12),(-51.13,-0.12),(-51.13,-0.11),(-51.14,-0.11)]),
    ]
    gpd.GeoDataFrame(
        {"classe": ["Floresta", "Pastagem"], "cod": [10, 20]},
        geometry=polygons, crs="EPSG:4674"
    ).to_file(gpkg, layer="uso_solo", driver="GPKG")
    payload = SimpleNamespace(
        selected_layers=["uso_solo"], class_fields={"uso_solo":"classe"},
        layer_colors={}, class_colors={}, title="Uso do Solo",
        subtitle="", source_text="Base de teste", include_branding=False,
        style=SimpleNamespace(model_dump=lambda: {"grid":"border","context":"balanced"}),
        property_name="Teste", municipality="Macapá", state="AP", responsible="Equipe de teste",
    )
    captured = {}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, _limit): return b"%PDF-1.4\\n" + b"0"*2000

    def fake_open(request, timeout):
        captured.update(json.loads(request.data.decode("utf-8")))
        return Response()

    with patch("urllib.request.urlopen", side_effect=fake_open):
        result = render_package_pyqgis(gpkg, payload, box(-51.16,-0.13,-51.12,-0.10),
                                      box(-51.16,-0.13,-51.12,-0.10))
    assert result.startswith(b"%PDF")
    layer = captured["layers"][0]
    assert layer["class_field"] == "amazonika_class"
    assert {c["value"] for c in layer["classes"]} == {"Floresta","Pastagem"}
    assert [f["properties"]["amazonika_class"] for f in layer["features"]] == ["Floresta","Pastagem"]
    assert captured["metadata"]["municipality"] == "Macapá"
    assert captured["layers"][-1]["role"] == "property"
