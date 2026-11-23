"""Paralela a cadeia de pontos P (PA1/PA2) com vários segmentos."""
import math
import unittest

from app.services.pa_offset_intersection import offset_polyline


def P(name, e, n, s=0.02, h=None, sh=None):
    d = {"name": name, "easting_m": e, "northing_m": n, "sigma_e_m": s, "sigma_n_m": s}
    if h is not None:
        d["ellipsoidal_height_m"] = h
    if sh is not None:
        d["sigma_h_m"] = sh
    return d


# Cadeia em "L": leste 100 m e depois norte 100 m.
L = [P("p1", 500000, 100000, h=10, sh=0.03), P("p2", 500100, 100000, h=11, sh=0.04),
     P("p3", 500100, 100100, h=12, sh=0.05)]


class OffsetPolylineTest(unittest.TestCase):
    def run_l(self, **kw):
        args = dict(method="PA1", offset_m=5, side="LEFT", offset_sigma_m=0.01,
                    utm_zone=22, hemisphere="N", sirgas2000_confirmed=True)
        args.update(kw)
        return offset_polyline(L, **args)

    def test_left_offset_of_l_shape(self):
        r = self.run_l()
        xy = [(v["easting_m"], v["northing_m"]) for v in r["vertices"]]
        # Esquerda de leste = norte; esquerda de norte = oeste.
        self.assertEqual(xy, [(500000, 100005), (500095, 100005), (500095, 100100)])
        self.assertEqual([v["support_point"] for v in r["vertices"]], ["p1", "p2", "p3"])
        self.assertEqual(r["operation"], "OFFSET_POLYLINE")
        self.assertFalse(r["ready_for_sigef"])

    def test_right_offset(self):
        r = self.run_l(side="RIGHT")
        xy = [(v["easting_m"], v["northing_m"]) for v in r["vertices"]]
        self.assertEqual(xy, [(500000, 99995), (500105, 99995), (500105, 100100)])

    def test_height_not_copied_from_support(self):
        r = self.run_l()
        self.assertTrue(all(v["height_m"] is None and v["sigma_h_m"] is None for v in r["vertices"]))
        self.assertEqual([v["support_height_m"] for v in r["vertices"]], [10, 11, 12])

    def test_sigma_propagated(self):
        r = self.run_l()
        corner = r["vertices"][1]
        self.assertEqual(r["sigma_model"], "FIRST_ORDER_UNCORRELATED")
        self.assertGreater(corner["sigma_horizontal_m"], 0.02)
        self.assertLess(corner["sigma_horizontal_m"], 0.1)
        # Ponta inicial: depende sobretudo de p1 (0,02) e do afastamento (0,01).
        start = r["vertices"][0]
        self.assertTrue(math.isclose(start["sigma_n_m"], math.sqrt(0.02**2 + 0.01**2), abs_tol=2e-3))

    def test_missing_sigma_means_no_propagation(self):
        r = self.run_l(offset_sigma_m=None)
        self.assertIsNone(r["sigma_model"])
        self.assertIsNone(r["vertices"][0]["sigma_horizontal_m"])

    def test_collinear_points(self):
        pts = [P("a", 0 + 500000, 100000), P("b", 500050, 100000), P("c", 500100, 100000)]
        r = offset_polyline(pts, method="PA2", offset_m=3, side="LEFT", offset_sigma_m=0)
        self.assertEqual([v["northing_m"] for v in r["vertices"]], [100003, 100003, 100003])

    def test_end_mode_none(self):
        r = self.run_l(end_mode="NONE")
        self.assertEqual(len(r["vertices"]), 1)
        self.assertEqual(r["vertices"][0]["support_point"], "p2")

    def test_geographic_coordinates(self):
        r = self.run_l()
        self.assertIsNotNone(r["vertices"][0]["latitude"])
        r2 = self.run_l(sirgas2000_confirmed=False)
        self.assertIsNone(r2["vertices"][0]["latitude"])

    def test_offset_too_large_inverts_segment(self):
        pts = [P("a", 500000, 100000), P("b", 500010, 100000), P("c", 500010, 100010),
               P("d", 500000, 100010)]
        with self.assertRaises(ValueError):
            offset_polyline(pts, method="PA1", offset_m=20, side="LEFT", offset_sigma_m=0)

    def test_validation(self):
        with self.assertRaises(ValueError):
            self.run_l(method="PS4")
        with self.assertRaises(ValueError):
            self.run_l(offset_m=0)
        with self.assertRaises(ValueError):
            self.run_l(side=None)
        with self.assertRaises(ValueError):
            offset_polyline([L[0], L[0]], method="PA1", offset_m=5, side="LEFT")
        with self.assertRaises(ValueError):
            offset_polyline(L[:2], method="PA1", offset_m=5, side="LEFT", end_mode="NONE")

    def test_sharp_return_rejected(self):
        pts = [P("a", 500000, 100000), P("b", 500100, 100000), P("c", 500000, 100001)]
        with self.assertRaises(ValueError):
            offset_polyline(pts, method="PA1", offset_m=1, side="LEFT")


if __name__ == "__main__":
    unittest.main()
