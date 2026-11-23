"""Paralela a cadeia de pontos P (PA1/PA2) com vários segmentos."""
import math
import unittest

from app.services.pa_offset_intersection import offset_polyline
from tests._sgl_fixture import P as _P, close, local

KW = dict(utm_zone=22, hemisphere="N", sirgas2000_confirmed=True)


def P(name, e, n, s=0.02, h=12.0, sh=None):
    return _P(name, e - 500000, n - 100000, s, h=h, sh=sh)


def xy(r):
    return [tuple(round(c, 2) for c in local(v)) for v in r["vertices"]]


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
        # Esquerda de leste = norte; esquerda de norte = oeste.
        self.assertEqual(xy(r), [(0, 5), (95, 5), (95, 100)])
        self.assertEqual([v["support_point"] for v in r["vertices"]], ["p1", "p2", "p3"])
        self.assertEqual(r["operation"], "OFFSET_POLYLINE")
        self.assertFalse(r["ready_for_sigef"])

    def test_right_offset(self):
        r = self.run_l(side="RIGHT")
        self.assertEqual(xy(r), [(0, -5), (105, -5), (105, 100)])

    def test_height_is_mean_of_reference_vertices(self):
        r = self.run_l()
        # Pontas: média dos 2 pontos do segmento; interno: média dos 3 pontos.
        self.assertEqual([v["height_m"] for v in r["vertices"]], [10.5, 11.0, 11.5])
        self.assertEqual(r["vertices"][1]["reference_points"], ["p1", "p2", "p3"])
        self.assertAlmostEqual(r["vertices"][0]["sigma_h_m"], math.sqrt(0.03**2 + 0.04**2) / 2, places=4)
        self.assertTrue(all(v["height_source"] == "MEAN_OF_REFERENCE_VERTICES" for v in r["vertices"]))

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
        r = offset_polyline(pts, method="PA2", offset_m=3, side="LEFT", offset_sigma_m=0, **KW)
        self.assertEqual([c[1] for c in xy(r)], [3, 3, 3])

    def test_end_mode_none(self):
        r = self.run_l(end_mode="NONE")
        self.assertEqual(len(r["vertices"]), 1)
        self.assertEqual(r["vertices"][0]["support_point"], "p2")

    def test_anchored_corners_stay_fixed(self):
        pts = [P("M1", 500000, 100000), P("p1", 500050, 100000), P("p2", 500100, 100000),
               P("p3", 500100, 100050), P("M2", 500100, 100100)]
        r = offset_polyline(pts, method="PA1", offset_m=5, side="LEFT", offset_sigma_m=0,
                            anchor_start=True, anchor_end=True, **KW)
        self.assertEqual([v["support_point"] for v in r["vertices"]], ["p1", "p2", "p3"])
        self.assertEqual(xy(r), [(50, 5), (95, 5), (95, 50)])
        self.assertEqual((r["anchor_start"], r["anchor_end"]), ("M1", "M2"))

    def test_missing_sigma_names_what(self):
        r = self.run_l(offset_sigma_m=None)
        self.assertTrue(any("desvio-padrão do afastamento" in w for w in r["warnings"]))

    def test_requires_sirgas_confirmation(self):
        with self.assertRaises(ValueError):
            self.run_l(sirgas2000_confirmed=False)

    def test_offset_too_large_inverts_segment(self):
        pts = [P("a", 500000, 100000), P("b", 500010, 100000), P("c", 500010, 100010),
               P("d", 500000, 100010)]
        with self.assertRaises(ValueError):
            offset_polyline(pts, method="PA1", offset_m=20, side="LEFT", offset_sigma_m=0, **KW)

    def test_validation(self):
        with self.assertRaises(ValueError):
            self.run_l(method="PS4")
        with self.assertRaises(ValueError):
            self.run_l(offset_m=0)
        with self.assertRaises(ValueError):
            self.run_l(side=None)
        with self.assertRaises(ValueError):
            offset_polyline([L[0], L[0]], method="PA1", offset_m=5, side="LEFT", **KW)
        with self.assertRaises(ValueError):
            offset_polyline(L[:2], method="PA1", offset_m=5, side="LEFT", end_mode="NONE", **KW)

    def test_sharp_return_rejected(self):
        pts = [P("a", 500000, 100000), P("b", 500100, 100000), P("c", 500000, 100001)]
        with self.assertRaises(ValueError):
            offset_polyline(pts, method="PA1", offset_m=1, side="LEFT", **KW)


if __name__ == "__main__":
    unittest.main()
