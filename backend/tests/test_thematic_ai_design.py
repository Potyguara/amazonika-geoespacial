"""The AI cartographic advisor must not invent fields, colors or geometries."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import geopandas as gpd
from shapely.geometry import Point
from app.api.routes import thematic_maps


class AdviserTests(unittest.TestCase):
    def test_validates_untrusted_model_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            ident="11111111-1111-4111-8111-111111111111"
            user=SimpleNamespace(id="u1")
            path=Path(tmp)/"u1"/(ident+".gpkg")
            path.parent.mkdir(parents=True)
            frame=gpd.GeoDataFrame({"classe":["Granulitos","Barreiras"]},
                geometry=[Point(-51.1,.01),Point(-51.2,.02)],crs="EPSG:4674")
            frame.to_file(path,layer="Geologia",driver="GPKG")
            req=thematic_maps.DesignRequest(package_id=ident,template="geologia",selected_layers=["Geologia"])
            # No API token: transparent local heuristic fallback.
            with patch.object(thematic_maps,"PACKAGE_ROOT",Path(tmp)),patch(
                "app.core.config.get_settings",return_value=SimpleNamespace(openai_api_key=None)):
                result=thematic_maps.design_map(req,user=user)
            self.assertFalse(result["ai_used"])
            self.assertEqual(result["design"][0]["class_field"],"classe")
            self.assertEqual(result["design"][0]["layer"],"Geologia")
