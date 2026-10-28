"""Mapbox gateway validation without network or credentials."""
import unittest
from unittest.mock import patch, Mock
from fastapi import HTTPException
from app.api.routes import mapbox_satellite as gateway


class MapboxSatelliteTests(unittest.TestCase):
    def test_disabled_by_default(self):
        with patch.object(gateway, "get_settings") as settings:
            settings.return_value.mapbox_satellite_enabled = False
            settings.return_value.mapbox_access_token = "fake"
            result = gateway.mapbox_status(user=None)
            self.assertFalse(result["enabled"])
            with self.assertRaises(HTTPException) as ctx:
                gateway.satellite_tile(z=2, x=1, y=1, user=None)
            self.assertEqual(ctx.exception.status_code, 503)

    def test_invalid_tile_rejected_before_network(self):
        with patch.object(gateway, "get_settings") as settings:
            settings.return_value.mapbox_satellite_enabled = True
            settings.return_value.mapbox_access_token = "fake"
            with self.assertRaises(HTTPException) as ctx:
                gateway.satellite_tile(z=2, x=12, y=1, user=None)
            self.assertEqual(ctx.exception.status_code, 422)

    def test_no_token_in_image_response(self):
        response = Mock()
        response.read.return_value = b"fake-jpg"
        response.headers.get.return_value = "image/jpeg"
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch.object(gateway, "get_settings") as settings, \
             patch.object(gateway, "urlopen", return_value=response):
            settings.return_value.mapbox_satellite_enabled = True
            settings.return_value.mapbox_access_token = "internal-only"
            tile = gateway.satellite_tile(z=2, x=1, y=1, user=None)
        self.assertEqual(tile.body, b"fake-jpg")
        self.assertNotIn(b"internal-only", tile.body)


if __name__ == "__main__":
    unittest.main()
