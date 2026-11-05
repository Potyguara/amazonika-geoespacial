"""MapBiomas Collection 11 adapter tests: no network, no credentials."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import rural_mapbiomas as mb
from app.api.routes import rural_diagnostics as routes

SUBJECT = {
    "type": "Polygon",
    "coordinates": [[[-51.2,-0.2],[-51.1,-0.2],[-51.1,-0.1],[-51.2,-0.1],[-51.2,-0.2]]],
}


def test_collection_11_asset_and_years():
    assert mb.COLLECTION == 11
    assert "collection11" in mb.ASSET_ID
    assert mb.MAX_YEAR == 2025
    assert mb.RESOLUTION_M == 30


def test_credentialless_configuration_does_not_reveal_secrets(monkeypatch):
    monkeypatch.setattr(mb, "get_settings", lambda: SimpleNamespace(
        gee_project_id=None,
        gee_service_account_email=None,
        gee_service_account_key_file=None,
    ))
    result = mb.gee_configuration()
    assert not result["enabled"]
    assert "service_account_email" not in result
    assert "key_file" not in result
    with pytest.raises(mb.MapBiomasError, match="não está habilitado"):
        mb._initialize_gee()


def test_geometry_and_extent_validation():
    assert mb.validate_geometry(SUBJECT).geom_type == "Polygon"
    for bad in [
        {"type":"Point","coordinates":[-51.1,-0.1]},
        {"type":"Polygon","coordinates":[[
            [-53,-1],[-52,-1],[-52,0],[-53,0],[-53,-1]
        ]]},
    ]:
        with pytest.raises(ValueError):
            mb.validate_geometry(bad)


def test_invalid_year_fails_before_connecting_gee(monkeypatch):
    monkeypatch.setattr(mb,"_initialize_gee",lambda: pytest.fail("should not authenticate"))
    with pytest.raises(ValueError, match="Ano indisponível"):
        mb.mapbiomas_preview(SUBJECT, 2026)


def test_class_area_results_and_unmapped_codes_are_not_invented():
    raw = {"groups": [
        {"class": 3, "sum": 200},
        {"class": 15, "sum": 100},
        {"class": 999, "sum": 20},
    ]}
    result = mb._normalize_statistics(raw, 2025, 330)
    assert result["classified_area_hectares"] == 320
    assert result["geometry_area_hectares"] == 330
    assert result["classes"][0]["name"] == "Formação Florestal"
    assert result["classes"][1]["name"] == "Pastagem"
    assert "consultar legenda" in result["classes"][2]["name"]
    assert sum(row["percent_classified"] for row in result["classes"]) == pytest.approx(100, abs=.01)


def test_rejects_missing_groups_duplicates_and_negative_class_area():
    for raw in [{}, {"groups": [{"class": 3, "sum": -1}]},
                {"groups": [{"class":3,"sum":10},{"class":3,"sum":5}]}]:
        with pytest.raises(mb.MapBiomasError):
            mb._normalize_statistics(raw, 2025, 50)


def test_api_maps_disabled_gee_to_503(monkeypatch):
    monkeypatch.setattr(routes, "mapbiomas_preview",
                        lambda *args: (_ for _ in ()).throw(
                            mb.MapBiomasError("Credenciais ausentes")
                        ))
    with pytest.raises(HTTPException) as err:
        routes.rural_mapbiomas_preview(routes.MapBiomasPreviewRequest(
            geometry=SUBJECT, year=2025))
    assert err.value.status_code == 503


def test_gee_reduce_uses_remote_pixel_area_and_grouped_classification():
    calls = []
    class FakeOutput:
        def getInfo(self):
            return {"groups":[{"class":3,"sum":15.5}]}
    class FakeImage:
        def select(self, key):
            calls.append(("select", key)); return self
        def rename(self,key):
            calls.append(("rename",key)); return self
        def divide(self,n):
            calls.append(("divide",n));return self
        def addBands(self,b):
            calls.append(("addBands", True));return self
        def reduceRegion(self,**kw):
            calls.append(("reduceRegion", kw)); return FakeOutput()
    class FakeReducer:
        def group(self,**kw):
            calls.append(("group", kw)); return self
    class FakeEE:
        Geometry = staticmethod(lambda geom,**kw: geom)
        Image = staticmethod(lambda asset: FakeImage())
        Reducer = SimpleNamespace(sum=lambda: FakeReducer())
    FakeEE.Image.pixelArea = lambda: FakeImage()
    result = mb._reduce_class_areas(FakeEE, SUBJECT, 2025)
    assert result["groups"][0]["sum"] == 15.5
    assert ("select","classification_2025") in calls
    assert ("group",{"groupField":1,"groupName":"class"}) in calls
    opts = next(v for k,v in calls if k=="reduceRegion")
    assert opts["scale"] == 30 and opts["bestEffort"] is False
    assert opts["maxPixels"] == mb.MAX_PIXELS
