"""Testes isolados da descoberta STAC: sem acessar a internet ou PostGIS."""
import unittest
from unittest.mock import patch
from io import BytesIO
from urllib.error import URLError

from app.api.routes.inpe_cbers import validate_bbox, summarize_item, search_scenes


class TestInpeCbers(unittest.TestCase):
    def test_bbox_valid(self):
        validate_bbox(-51.1, -0.2, -51.0, -0.1)

    def test_bbox_rejects_inverted_and_excessive(self):
        for bounds in [(-51, 1, -52, 2), (-53, -1, -50, 0), (-51, 10, -50, 10)]:
            with self.assertRaises(ValueError):
                validate_bbox(*bounds)

    def test_scene_requires_accuracy_review(self):
        scene = summarize_item({"id": "abc", "properties": {"datetime": "2026-01-01T00:00:00Z"}, "assets": {"BAND0": {"href": "https://data.inpe.br/example.tif"}}}, "CB4A-WPM-L4-DN-1")
        self.assertEqual(scene["ps4_status"], "PENDING_ACCURACY_EVIDENCE")
        self.assertEqual(scene["ortho_status"], "L4_DECLARED")

    def test_search_limits_upstream_and_does_not_certify(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, n): return b'{"type":"FeatureCollection","features":[{"id":"scene","properties":{},"assets":{}}]}'
        with patch("app.api.routes.inpe_cbers.urlopen", return_value=Response()) as get:
            result = search_scenes((-51.1, -0.2, -51, -0.1), "rgb", 2)
        self.assertFalse(result["certifiable"])
        self.assertEqual(len(result["scenes"]), 1)
        self.assertIn("collections/CB4A-WPM-PCA-FUSED-1/items", get.call_args.args[0].full_url)

    def test_upstream_outage(self):
        with patch("app.api.routes.inpe_cbers.urlopen", side_effect=URLError("down")):
            with self.assertRaises(RuntimeError):
                search_scenes((-51.1, -0.2, -51, -0.1), "ortho")


if __name__ == "__main__":
    unittest.main()
