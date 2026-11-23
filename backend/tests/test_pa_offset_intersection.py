"""Interseção de paralelas (PA1/PA2) no SGL, com sigma propagado e h média."""
import math
import unittest

from app.services.pa_offset_intersection import LocalFrame, intersect_offset_lines
from tests._sgl_fixture import P, close, local

KW = dict(utm_zone=22, hemisphere="N", sirgas2000_confirmed=True)


def lines(s=None, d1=10.0, d2=20.0, side1="LEFT", side2="RIGHT", sd=None, sh=None):
    # Reta 1 ao longo de e (A→B para leste); esquerda = norte.
    # Reta 2 ao longo de n (C→D para norte); direita = leste.
    return [
        {"points": [P("p1", 0, 0, s, h=10, sh=sh), P("p2", 100, 0, s, h=12, sh=sh)],
         "offset_m": d1, "side": side1, "offset_sigma_m": sd},
        {"points": [P("p3", 50, -100, s, h=14, sh=sh), P("p4", 50, 100, s, h=16, sh=sh)],
         "offset_m": d2, "side": side2, "offset_sigma_m": sd},
    ]


class OffsetLinesIntersectionTests(unittest.TestCase):
    def test_intersecao_de_paralelas_no_sgl(self):
        r = intersect_offset_lines(lines(), method="PA1", **KW)
        self.assertTrue(close(local(r), (70, 10)), local(r))
        self.assertEqual((r["vertex_type"], r["method"], r["operation"]), ("V", "PA1", "OFFSET_LINES_INTERSECTION"))
        self.assertFalse(r["ready_for_sigef"])
        self.assertEqual(r["calculation_frame"]["frame"], "SGL_GRS80")
        self.assertIsNotNone(r["easting_m"])

    def test_altitude_e_media_dos_vertices_de_referencia(self):
        r = intersect_offset_lines(lines(sh=0.04), method="PA1", **KW)
        self.assertAlmostEqual(r["height_m"], 13.0, places=4)
        self.assertEqual(r["height_source"], "MEAN_OF_REFERENCE_VERTICES")
        self.assertAlmostEqual(r["sigma_h_m"], math.sqrt(4 * 0.04**2) / 4, places=4)

    def test_sem_sigma_h_nao_inventa(self):
        r = intersect_offset_lines(lines(), method="PA1", **KW)
        self.assertIsNone(r["sigma_h_m"])

    def test_afastamento_zero_e_o_proprio_alinhamento(self):
        r = intersect_offset_lines(lines(d1=0, d2=0, side1=None, side2=None), method="PA2", **KW)
        self.assertTrue(close(local(r), (50, 0)))

    def test_lados_opostos(self):
        r = intersect_offset_lines(lines(side1="RIGHT", side2="LEFT"), method="PA1", **KW)
        self.assertTrue(close(local(r), (30, -10)))

    def test_sigma_propagado_quando_todos_informados(self):
        r = intersect_offset_lines(lines(s=0.002, sd=0.0), method="PA1", **KW)
        self.assertEqual(r["sigma_model"], "FIRST_ORDER_UNCORRELATED")
        self.assertTrue(0 < r["sigma_horizontal_m"] < 0.01)
        self.assertAlmostEqual(r["sigma_horizontal_m"], math.hypot(r["sigma_e_m"], r["sigma_n_m"]), places=4)

    def test_sigma_do_afastamento_entra_na_propagacao(self):
        sem = intersect_offset_lines(lines(s=0.002, sd=0.0), method="PA1", **KW)
        com = intersect_offset_lines(lines(s=0.002, sd=0.10), method="PA1", **KW)
        self.assertGreater(com["sigma_horizontal_m"], sem["sigma_horizontal_m"] + 0.05)

    def test_sem_sigma_nao_inventa_precisao(self):
        r = intersect_offset_lines(lines(), method="PA1", **KW)
        self.assertIsNone(r["sigma_e_m"])
        self.assertIsNone(r["sigma_model"])
        self.assertTrue(any("não propagados" in w for w in r["warnings"]))

    def test_metodo_obrigatorio(self):
        with self.assertRaisesRegex(ValueError, "PA1 ou PA2"):
            intersect_offset_lines(lines(), method="PB1", **KW)

    def test_lado_obrigatorio_com_afastamento(self):
        with self.assertRaisesRegex(ValueError, "lado"):
            intersect_offset_lines(lines(side1=None), method="PA1", **KW)

    def test_retas_quase_paralelas(self):
        data = lines()
        data[1]["points"] = [P("p3", 0, 50), P("p4", 100, 51)]
        with self.assertRaisesRegex(ValueError, "quase paralelas"):
            intersect_offset_lines(data, method="PA1", **KW)

    def test_exige_sirgas_confirmado(self):
        with self.assertRaisesRegex(ValueError, "SIRGAS2000"):
            intersect_offset_lines(lines(), method="PA1")

    def test_exige_altitude_dos_pontos(self):
        data = lines()
        del data[0]["points"][0]["ellipsoidal_height_m"]
        with self.assertRaisesRegex(ValueError, "altitude elipsoidal"):
            intersect_offset_lines(data, method="PA1", **KW)

    def test_aceita_utm_quando_sem_geograficas(self):
        ref = intersect_offset_lines(lines(), method="PA1", **KW)
        data = lines()
        for line, (a, b) in zip(data, [(0, 1), (0, 1)]):
            for p in line["points"]:
                e, n = _utm(p)
                p.pop("latitude"); p.pop("longitude")
                p.update(easting_m=e, northing_m=n)
        r = intersect_offset_lines(data, method="PA1", **KW)
        self.assertAlmostEqual(r["latitude"], ref["latitude"], places=8)


def _utm(p):
    from pyproj import Transformer
    t = Transformer.from_crs("EPSG:4674", "EPSG:31976", always_xy=True)
    return t.transform(p["longitude"], p["latitude"])


class LocalFrameTests(unittest.TestCase):
    def test_ida_e_volta(self):
        f = LocalFrame([(-51.0, 0.0, 10.0), (-51.001, 0.001, 20.0)])
        e, n, u = f.to_local(-51.0005, 0.0004, 15.0)
        lon, lat, h = f.to_geodetic(e, n, u)
        self.assertAlmostEqual(lon, -51.0005, places=10)
        self.assertAlmostEqual(lat, 0.0004, places=10)
        self.assertAlmostEqual(h, 15.0, places=5)


if __name__ == "__main__":
    unittest.main()
