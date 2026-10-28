"""Tile budget validation for provider and limit controls."""
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from app.services import tile_budget


class BudgetTests(unittest.TestCase):
    def test_period_uses_utc_month(self):
        self.assertRegex(tile_budget._period(), r"^\d{4}-\d{2}$")

    def test_invalid_provider_fails_closed(self):
        with self.assertRaises(HTTPException) as result:
            tile_budget.reserve("arbitrary")
        self.assertEqual(result.exception.status_code, 422)

    def test_invalid_limits_rejected(self):
        with self.assertRaises(HTTPException) as result:
            tile_budget.update("mapbox", True, 0)
        self.assertEqual(result.exception.status_code, 422)
        with self.assertRaises(HTTPException):
            tile_budget.update("google", True, 10000001)


if __name__ == "__main__":
    unittest.main()
