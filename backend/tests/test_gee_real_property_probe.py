"""Offline tests for the controlled single-property MapBiomas smoke script."""
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "rural_gee_smoke", Path(__file__).resolve().parents[2] / "scripts" /
    "probe_mapbiomas_real_property.py"
)
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)

SMALL = {"type":"Polygon","coordinates":[[
    [-51.12,0.03],[-51.118,0.03],[-51.118,0.032],
    [-51.12,0.032],[-51.12,0.03]
]]}
LARGE = {"type":"Polygon","coordinates":[[
    [-51.2,0.03],[-51.1,0.03],[-51.1,0.13],
    [-51.2,0.13],[-51.2,0.03]
]]}


def test_requires_explicit_opt_in_before_looking_up_property(monkeypatch):
    monkeypatch.delenv("GEE_ALLOW_REAL_PROPERTY_TEST", raising=False)
    monkeypatch.setattr(smoke, "choose_property", lambda *a, **kw: pytest.fail("lookup"))
    with pytest.raises(ValueError, match="não autorizado"):
        smoke.run_property_test(car_code="not-queried", latitude=None,
                                longitude=None, year=2025, max_hectares=100)


def test_refuses_oversize_before_billable_processing(monkeypatch):
    monkeypatch.setenv("GEE_ALLOW_REAL_PROPERTY_TEST", "yes")
    monkeypatch.setenv("GEE_PROJECT_ID", "amazonika-geoespacial")
    monkeypatch.setattr(smoke, "choose_property",
                        lambda *a, **kw: {"geometry": LARGE})
    from app.services import rural_mapbiomas as mb
    monkeypatch.setattr(mb, "_initialize_gee", lambda: pytest.fail("GEE called"))
    with pytest.raises(ValueError, match="excede limite"):
        smoke.run_property_test(car_code="dummy", latitude=None,
                                longitude=None, year=2025, max_hectares=100)


def test_one_real_property_invokes_one_reduction(monkeypatch):
    monkeypatch.setenv("GEE_ALLOW_REAL_PROPERTY_TEST", "yes")
    monkeypatch.setenv("GEE_PROJECT_ID", "amazonika-geoespacial")
    monkeypatch.setattr(smoke, "choose_property",
                        lambda *a, **kw: {"geometry": SMALL})
    from app.services import rural_mapbiomas as mb
    monkeypatch.setattr(mb, "_initialize_gee", lambda: object())
    calls = []
    def reduce(ee, geometry, year, *, max_pixels):
        assert max_pixels == 30_000
        calls.append((geometry,year))
        return {"groups":[{"class":24,"sum":3.9815},{"class":11,"sum":0.9087}]}
    monkeypatch.setattr(mb, "_reduce_class_areas", reduce)
    result = smoke.run_property_test(
        car_code="dummy", latitude=None, longitude=None,
        year=2025, max_hectares=100,
    )
    assert len(calls) == 1
    assert calls[0][1] == 2025
    assert result["status"] == "ANALYZED"
    assert result["classes"][0]["name"] == "Área Urbanizada"


def test_limit_beyond_1500_hectares_is_rejected(monkeypatch):
    monkeypatch.setenv("GEE_ALLOW_REAL_PROPERTY_TEST", "yes")
    monkeypatch.setenv("GEE_PROJECT_ID", "amazonika-geoespacial")
    with pytest.raises(ValueError, match="entre 1 e 1500"):
        smoke.run_property_test(car_code="dummy",latitude=None,
                                longitude=None,year=2025,max_hectares=1501)


def test_car_service_error_does_not_run_earth_engine(monkeypatch):
    monkeypatch.setenv("GEE_ALLOW_REAL_PROPERTY_TEST", "yes")
    monkeypatch.setenv("GEE_PROJECT_ID", "amazonika-geoespacial")
    from app.services import rural_mapbiomas as mb
    from app.services.rural_official_car import OfficialCarQueryError
    def fail_lookup(*args, **kwargs):
        raise OfficialCarQueryError("SICAR WFS indisponível ou inacessível.")
    monkeypatch.setattr(smoke, "choose_property", fail_lookup)
    monkeypatch.setattr(mb, "_initialize_gee", lambda: pytest.fail("Earth Engine invoked"))
    with pytest.raises(OfficialCarQueryError, match="SICAR WFS"):
        smoke.run_property_test(
            car_code="dummy", latitude=None, longitude=None,
            year=2025, max_hectares=100,
        )


def test_large_property_requires_second_opt_in(monkeypatch):
    monkeypatch.setenv("GEE_ALLOW_REAL_PROPERTY_TEST", "yes")
    monkeypatch.setenv("GEE_PROJECT_ID", "amazonika-geoespacial")
    monkeypatch.delenv("GEE_ALLOW_LARGE_PROPERTY_TEST", raising=False)
    monkeypatch.setattr(smoke, "choose_property", lambda *a, **kw: pytest.fail("lookup"))
    with pytest.raises(ValueError, match="GEE_ALLOW_LARGE_PROPERTY_TEST"):
        smoke.run_property_test(
            car_code="dummy", latitude=None, longitude=None,
            year=2025, max_hectares=1200,
        )


def test_large_property_runs_once_with_30k_pixel_bound(monkeypatch):
    from shapely.geometry import mapping
    from shapely import affinity
    from app.services import rural_mapbiomas as mb
    # Roughly 1200 ha at the equator, below 1500ha and 30k pixels.
    polygon = {"type": "Polygon", "coordinates": [[
        [-51.2, 0], [-51.17, 0], [-51.17, 0.032],
        [-51.2, 0.032], [-51.2, 0],
    ]]}
    monkeypatch.setenv("GEE_ALLOW_REAL_PROPERTY_TEST", "yes")
    monkeypatch.setenv("GEE_ALLOW_LARGE_PROPERTY_TEST", "yes")
    monkeypatch.setenv("GEE_PROJECT_ID", "amazonika-geoespacial")
    monkeypatch.setattr(smoke, "choose_property", lambda *a, **kw: {"geometry": polygon})
    monkeypatch.setattr(mb, "_initialize_gee", lambda: object())
    calls = []
    def reduce(ee, geometry, year, *, max_pixels):
        calls.append((geometry, year, max_pixels))
        return {"groups": [{"class": 3, "sum": 1100}]}
    monkeypatch.setattr(mb, "_reduce_class_areas", reduce)
    output = smoke.run_property_test(
        car_code="dummy", latitude=None, longitude=None,
        year=2025, max_hectares=1500,
    )
    assert len(calls) == 1
    assert calls[0][2] == 30000
    assert 1000 < output["geometry_area_hectares"] < 1500
