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

    def test_attribution_viewport_validation(self):
        with self.assertRaises(HTTPException):
            google_tiles.google_tiles_attribution(
                north=-10, south=10, east=-20, west=-30, zoom=8, user=None
            )


if __name__ == "__main__":
    unittest.main()
