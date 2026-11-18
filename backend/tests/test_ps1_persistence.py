import unittest
from copy import deepcopy
from app.services.ps1_persistence import same_perimeter


class PS1PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.points = [
            dict(sigef_vertex_code="TEST-M-0001", longitude=-51.41234567891, latitude=.4, sigef_method="PG1", sigma_lon_m=.01),
            dict(sigef_vertex_code="TEST-V-0001", longitude=-51.41123456789, latitude=.39, sigef_method="PS1", sigma_lon_m=.1),
        ]

    def test_serialization(self):
        restored = deepcopy(self.points)
        for p in restored:
            p["longitude"] = round(p["longitude"], 9)
            p["latitude"] = round(p["latitude"], 9)
            p["confrontant_cns"] = ""
        self.assertTrue(same_perimeter(self.points, restored))

    def test_changed_sigma(self):
        altered = deepcopy(self.points)
        altered[1]["sigma_lon_m"] = .01
        self.assertFalse(same_perimeter(self.points, altered))

    def test_changed_coordinate(self):
        altered = deepcopy(self.points)
        altered[1]["latitude"] += .000001
        self.assertFalse(same_perimeter(self.points, altered))

    def test_missing_or_reordered(self):
        self.assertFalse(same_perimeter(self.points, self.points[:1]))
        self.assertFalse(same_perimeter(self.points, list(reversed(self.points))))

    def test_changed_mark(self):
        altered = deepcopy(self.points)
        altered[0]["sigef_vertex_code"] = "OTHER-M-0001"
        self.assertFalse(same_perimeter(self.points, altered))
