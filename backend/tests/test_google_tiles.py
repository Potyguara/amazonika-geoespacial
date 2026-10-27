"""Offline checks for the opt-in Google Map Tiles integration."""
from __future__ import annotations
import json
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from app.api.routes import google_tiles


class GoogleTilesTests(unittest.TestCase):
    def setUp(self):
        google_tiles._session.clear()

    def test_disabled_without_explicit_opt_in(self):
        with patch.object(google_tiles, "get_settings") as settings:
            settings.return_value.google_map_tiles_enabled = False
            settings.return_value.google_maps_api_key = "dummy"
            with self.assertRaises(HTTPException) as raised:
                google_tiles._key()
        self.assertEqual(raised.exception.status_code, 503)

    def test_missing_key_blocks_enabled_gateway(self):
        with patch.object(google_tiles, "get_settings") as settings:
            settings.return_value.google_map_tiles_enabled = True
            settings.return_value.google_maps_api_key = None
            with self.assertRaises(HTTPException) as raised:
                google_tiles._key()
        self.assertEqual(raised.exception.status_code, 503)

    def test_valid_session_reused_and_never_returns_key(self):
        with patch.object(google_tiles, "_fetch_google") as upstream:
            upstream.return_value = (
                json.dumps({"session": "opaque-token", "expiry": 1999999999}).encode(),
                "application/json",
            )
            a = google_tiles._current_session()
            b = google_tiles._current_session()
            self.assertEqual(a["token"], b["token"])
            upstream.assert_called_once()
            self.assertNotIn("key", json.dumps(a))

    def test_tile_coordinates_validated_before_upstream(self):
        with self.assertRaises(HTTPException):
            google_tiles.google_tiles_tile(zoom=4, x=9999, y=0, user=None)
        with self.assertRaises(HTTPException):
            google_tiles.google_tiles_tile(zoom=-1, x=0, y=0, user=None)

    def test_viewport_uses_documented_tile_prefix(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.read.return_value = b'{"copyright":"Imagery credit"}'
        response.headers.get.return_value = "application/json"
        response.__enter__.return_value = response
        with patch.object(google_tiles, "_key", return_value="dummy"), \
             patch.object(google_tiles, "urlopen", return_value=response) as request:
            data, mime = google_tiles._fetch_google("viewport", {
                "session": "placeholder", "zoom": 10,
                "north": 1, "south": 0, "east": 1, "west": 0,
            })
        self.assertEqual(json.loads(data)["copyright"], "Imagery credit")
        self.assertIn("tile.googleapis.com/tile/v1/viewport?", request.call_args.args[0].full_url)
        self.assertEqual(mime, "application/json")

    def test_attribution_viewport_validation(self):
        with self.assertRaises(HTTPException):
            google_tiles.google_tiles_attribution(
                north=-10, south=10, east=-20, west=-30, zoom=8, user=None
            )


if __name__ == "__main__":
    unittest.main()
