"""Live GeoPackage -> API serializer -> PyQGIS -> PDF regression.

Requires CARTOGRAPHY_URL pointing to a running cartography worker.
This test does not use production storage or credentials.
"""
import os
import time
import urllib.request
from types import SimpleNamespace

import geopandas as gpd
from shapely.geometry import Polygon, box

from app.services.thematic_pyqgis_package import render_package_pyqgis


def test_live_geopackage_to_pyqgis_pdf(tmp_path):
    endpoint = os.environ["CARTOGRAPHY_URL"].rstrip("/")
    deadline = time.monotonic() + 90
    while True:
        try:
            with urllib.request.urlopen(endpoint + "/health", timeout=3) as response:
                if response.status == 200:
                    break
        except OSError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(1)

    gpkg = tmp_path / "teste_integracao.gpkg"
    features = gpd.GeoDataFrame(
        {"classe": ["Floresta", "Pastagem"], "codigo": [101, 102]},
        geometry=[
            Polygon([(-51.149,-0.118),(-51.140,-0.118),(-51.140,-0.110),(-51.149,-0.110)]),
            Polygon([(-51.139,-0.118),(-51.133,-0.118),(-51.133,-0.112),(-51.139,-0.112)]),
        ],
        crs="EPSG:4674",
    )
    features.to_file(gpkg, layer="uso_solo", driver="GPKG")
    payload = SimpleNamespace(
        selected_layers=["uso_solo"],
        class_fields={"uso_solo": "classe"},
        class_colors={}, layer_colors={},
        title="MAPA DE USO DO SOLO - TESTE INTEGRADO",
        subtitle="GeoPackage e PyQGIS reais",
        source_text="Geometrias artificiais de homologação",
        include_branding=True,
        property_name="Imóvel de teste",
        municipality="Macapá",
        state="AP",
        responsible="Homologação (fictício)",
        style=SimpleNamespace(model_dump=lambda: {"grid": "border", "context": "balanced"}),
    )
    prop = box(-51.15,-0.12,-51.13,-0.10)
    roi = box(-51.16,-0.13,-51.12,-0.09)
    pdf = render_package_pyqgis(gpkg, payload, prop, roi)
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 5000
    target = os.environ.get("CARTOGRAPHY_TEST_PDF")
    if target:
        with open(target, "wb") as output:
            output.write(pdf)
    print("PYQGIS_GPKG_E2E_OK",len(pdf),"bytes")
