import unittest
from app.services.ps1_consolidation import consolidate_ps1


class PS1ConsolidationTests(unittest.TestCase):
    def setUp(self):
        self.boundary = [
            dict(name="A", sigef_vertex_code="TEST-M-0001", longitude=-51.4, latitude=.4, parcel_number="1", boundary_type="LA6", confrontant="Teste"),
            dict(name="B", sigef_vertex_code="TEST-M-0002", longitude=-51.39, latitude=.39, parcel_number="1"),
            dict(name="C", sigef_vertex_code="TEST-M-0003", longitude=-51.41, latitude=.39, parcel_number="1"),
        ]
        self.vertices = [dict(code="TEST-V-0001", longitude=-51.395, latitude=.395)]
        self.checks = [dict(id="C1", used_for_control=False, delta_e_m=.1, delta_n_m=.2, delta_h_m=.3)]

    def calculate(self, kind="ELLIPSOIDAL"):
        return consolidate_ps1(self.boundary, "TEST-M-0001", self.vertices, self.checks, "ARTIFICIAL", kind, lambda lon, lat: 12.)

    def test_preserve_and_insert(self):
        r = self.calculate()
        self.assertEqual(len(r["vertices"]), 4)
        self.assertEqual(r["vertices"][0], self.boundary[0])
        self.assertEqual(r["vertices"][2:], self.boundary[1:])
        v = r["generated"][0]
        self.assertEqual(v["sigef_method"], "PS1")
        self.assertAlmostEqual(v["sigma_lon_m"], .1)
        self.assertAlmostEqual(v["ellipsoidal_height_m"], 12.)
        self.assertFalse(v["height_reference_confirmed"])
        self.assertFalse(r["ready_for_sigef"])

    def test_bad_accuracy(self):
        self.checks[0]["delta_e_m"] = 2
        with self.assertRaises(ValueError):
            self.calculate()

    def test_missing_vertical_factor(self):
        with self.assertRaises(ValueError):
            self.calculate("NORMAL")

    def test_normal_height(self):
        self.vertices[0].update(factor=-3., factor_sigma=.4)
        v = self.calculate("NORMAL")["generated"][0]
        self.assertAlmostEqual(v["ellipsoidal_height_m"], 9.)
        self.assertAlmostEqual(v["derived_physical_altitude_m"], 12.)
        self.assertAlmostEqual(v["sigma_h_m"], .5)

    def test_repeated_code(self):
        self.vertices.append(dict(self.vertices[0], longitude=-51.394, latitude=.394))
        with self.assertRaises(ValueError):
            self.calculate()
