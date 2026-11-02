"""Regression for owned GeoPackage field discovery."""
from types import SimpleNamespace

import geopandas as gpd
from shapely.geometry import box
from fastapi import HTTPException
import pytest

from app.api.routes import thematic_maps


def test_package_fields_reads_only_owned_package(tmp_path, monkeypatch):
    monkeypatch.setattr(thematic_maps, "PACKAGE_ROOT", tmp_path)
    user = SimpleNamespace(id="teste-usuario")
    package_id = "2b672d77-0123-4dd6-b828-148f4946120c"
    path = thematic_maps._user_package(user, package_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame(
        {"classe": ["Floresta"], "codigo": [7]},
        geometry=[box(-51.15,-0.12,-51.14,-0.11)], crs="EPSG:4674"
    ).to_file(path, layer="uso_solo", driver="GPKG")
    result = thematic_maps.package_fields(package_id, user=user)
    assert result["package_id"] == package_id
    assert result["layers"][0]["name"] == "uso_solo"
    assert {"classe", "codigo"} <= {f["name"] for f in result["layers"][0]["fields"]}
    with pytest.raises(HTTPException) as exc:
        thematic_maps.package_fields("a660670f-615a-4416-a3d1-5fa9b1d462b2", user=user)
    assert exc.value.status_code == 404

def test_package_classes_counts_and_access(tmp_path, monkeypatch):
    monkeypatch.setattr(thematic_maps, "PACKAGE_ROOT", tmp_path)
    user = SimpleNamespace(id="teste-usuario")
    package_id = "1f3c679d-2223-4a3a-a857-0c79fa5315ef"
    path = thematic_maps._user_package(user, package_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame(
        {"classe": ["Floresta", "Pastagem", "Floresta"]},
        geometry=[box(-51.15 + i*.01,-.12,-51.14 + i*.01,-.11) for i in range(3)],
        crs="EPSG:4674"
    ).to_file(path, layer="uso_solo", driver="GPKG")
    result = thematic_maps.package_classes(package_id, "uso_solo", "classe", user=user)
    assert result["total_features"] == 3
    assert {entry["value"]: entry["count"] for entry in result["classes"]} == {
        "Floresta": 2, "Pastagem": 1
    }
    with pytest.raises(HTTPException) as exc:
        thematic_maps.package_classes(package_id, "uso_solo", "inexistente", user=user)
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException) as exc:
        thematic_maps.package_classes("a660670f-615a-4416-a3d1-5fa9b1d462b2", "uso_solo", "classe", user=user)
    assert exc.value.status_code == 404
