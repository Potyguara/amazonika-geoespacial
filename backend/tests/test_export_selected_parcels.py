import io
import zipfile

import geopandas as gpd
import pytest

from app.services.geospatial_export import export_polygon
from app.services.parcel_selection_export import export_parcels

SQUARE_XYZ = {"type": "Polygon", "coordinates": [[
    [-51.0, 0.1, 12.5], [-51.0, 0.2, 12.5], [-50.9, 0.2, 12.5], [-50.9, 0.1, 12.5], [-51.0, 0.1, 12.5],
]]}
MULTI = {"type": "MultiPolygon", "coordinates": [
    [[[-50.0, 0.0], [-50.0, 0.01], [-49.99, 0.01], [-50.0, 0.0]]],
    [[[-49.9, 0.0], [-49.9, 0.01], [-49.89, 0.01], [-49.9, 0.0]]],
]}


@pytest.mark.parametrize("fmt", ["txt", "kml", "shp"])
def test_individual_export_accepts_xyz(fmt):
    # Antes: "too many values to unpack (expected 2)" com vértices com altitude.
    data, _, _ = export_polygon(geometry=SQUARE_XYZ, filename="Poligono 1", format=fmt)
    assert data


def _parcels():
    return [
        {"name": "Parcela SIGEF", "layer": "SIGEF — Público", "geometry": SQUARE_XYZ,
         "properties": {"parcela_codigo": "abc-123", "nome_area": "Fazenda Ação"}},
        {"name": "Lote 7", "layer": "Lotes Assentamentos Amapá", "geometry": MULTI,
         "properties": {"lote": 7, "parcela_codigo_secundario": "x"}},
    ]


def test_kml_contains_every_parcel_with_attributes():
    data, name, media = export_parcels(parcels=_parcels(), filename="Seleção", format="kml")
    text = data.decode("utf-8")
    assert name.endswith(".kml") and "kml" in media
    assert text.count("<Placemark>") == 2
    assert "<MultiGeometry>" in text
    assert "Fazenda Ação" in text and "abc-123" in text


def test_shapefile_zip_contains_every_parcel(tmp_path):
    data, name, _ = export_parcels(parcels=_parcels(), filename="Seleção", format="shp")
    assert name.endswith(".zip")
    archive = zipfile.ZipFile(io.BytesIO(data))
    names = set(archive.namelist())
    assert {"parcelas.shp", "parcelas.dbf", "parcelas.shx", "parcelas.prj", "atributos.csv"} <= names
    archive.extractall(tmp_path)
    frame = gpd.read_file(tmp_path / "parcelas.shp")
    assert len(frame) == 2
    assert list(frame["NOME"]) == ["Parcela SIGEF", "Lote 7"]
    assert frame.loc[0, "NOME_AREA"] == "Fazenda Ação"
    # Campos truncados a 10 caracteres continuam únicos.
    assert "PARCELA_CO" in frame.columns and "PARCELA_C1" in frame.columns
    assert frame.loc[0, "AREA_HA"] > 0


def test_rejects_non_polygon():
    with pytest.raises(ValueError):
        export_parcels(parcels=[{"name": "p", "geometry": {"type": "Point", "coordinates": [0, 0]}}],
                       filename="x", format="kml")
