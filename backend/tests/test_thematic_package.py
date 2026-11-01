"""Regression for thematic GeoPackage batches and optional branding."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import geopandas as gpd
from shapely.geometry import Point, Polygon
from app.api.routes import thematic_maps


class ThematicPackageTests(unittest.TestCase):
    def test_route_import_has_no_unlisted_fiona_dependency(self):
        from app.api.router import api_router
        self.assertTrue(any(route.path.endswith("/thematic-maps/package") for route in api_router.routes))

    def test_package_renders_with_separate_property(self):
        with tempfile.TemporaryDirectory() as directory:
            name = "11111111-1111-4111-8111-111111111111"
            user = SimpleNamespace(id="u-test")
            gpkg = Path(directory) / "u-test" / (name + ".gpkg")
            gpkg.parent.mkdir(parents=True)
            points = gpd.GeoDataFrame({"nome":["Local 1","Local 2"]},
                geometry=[Point(-51.1, -.02), Point(-51.08, -.02)],crs="EPSG:4674")
            points.to_file(gpkg,layer="localidades",driver="GPKG")
            polygon = Polygon([(-51.11,-.03),(-51.07,-.03),(-51.07,-.01),(-51.11,-.01),(-51.11,-.03)])
            request = thematic_maps.PackageMapRequest(
                package_id=name, title="Mapa de situação", selected_layers=["localidades"],
                include_branding=False, property_geometry=polygon.__geo_interface__)
            with patch.object(thematic_maps,"PACKAGE_ROOT",Path(directory)):
                result=thematic_maps.render_package_pdf(request,user=user)
                self.assertTrue(result.body.startswith(b"%PDF"))
                self.assertGreater(len(result.body),2000)

    def test_invalid_package_path(self):
        user=SimpleNamespace(id="test")
        with self.assertRaises(Exception):
            thematic_maps._user_package(user,"../../escape")
