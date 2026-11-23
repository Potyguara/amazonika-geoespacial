"""Interseção de paralelas (PA1/PA2) sem clique, com sigma propagado."""
import math
import unittest
from app.services.pa_offset_intersection import intersect_offset_lines


def P(name, e, n, s=None):
    d = {"name": name, "easting_m": e, "northing_m": n}
    if s is not None:
        d.update(sigma_e_m=s, sigma_n_m=s)
    return d


def lines(s=None, d1=10.0, d2=20.0, side1="LEFT", side2="RIGHT", sd=None):
    # Reta 1 ao longo do eixo E (A→B para leste); esquerda = norte.
    # Reta 2 ao longo do eixo N (C→D para norte); direita = leste.
    return [
        {"points": [P("p1", 500000, 100000, s), P("p2", 500100, 100000, s)],
         "offset_m": d1, "side": side1, "offset_sigma_m": sd},
        {"points": [P("p3", 500050, 99900, s), P("p4", 500050, 100100, s)],
         "offset_m": d2, "side": side2, "offset_sigma_m": sd},
    ]


def _approx(expected, abs=1e-6):
    class _A:
        def __eq__(self, other):
            if isinstance(expected, tuple):
                return all(math.isclose(a, b, abs_tol=abs) for a, b in zip(other, expected))
            return math.isclose(other, expected, abs_tol=abs)
    return _A()


class OffsetLinesIntersectionTests(unittest.TestCase):
    def test_intersecao_de_paralelas(self):
        r = intersect_offset_lines(lines(), method="PA1")
        assert r["easting_m"] == _approx(500070)
        assert r["northing_m"] == _approx(100010)
        assert r["vertex_type"] == "V" and r["method"] == "PA1"
        assert r["operation"] == "OFFSET_LINES_INTERSECTION"
        assert r["ready_for_sigef"] is False and r["height_m"] is None


    def test_afastamento_zero_e_o_proprio_alinhamento(self):
        r = intersect_offset_lines(lines(d1=0, d2=0, side1=None, side2=None), method="PA2")
        assert (r["easting_m"], r["northing_m"]) == _approx((500050, 100000))


    def test_lados_opostos(self):
        r = intersect_offset_lines(lines(side1="RIGHT", side2="LEFT"), method="PA1")
        assert (r["easting_m"], r["northing_m"]) == _approx((500030, 99990))


    def test_sigma_propagado_quando_todos_informados(self):
        r = intersect_offset_lines(lines(s=0.002, sd=0.0), method="PA1")
        assert r["sigma_model"] == "FIRST_ORDER_UNCORRELATED"
        assert 0 < r["sigma_horizontal_m"] < 0.01
        assert r["sigma_horizontal_m"] == _approx(math.hypot(r["sigma_e_m"], r["sigma_n_m"]), abs=1e-4)


    def test_sigma_do_afastamento_entra_na_propagacao(self):
        sem = intersect_offset_lines(lines(s=0.002, sd=0.0), method="PA1")
        com = intersect_offset_lines(lines(s=0.002, sd=0.10), method="PA1")
        assert com["sigma_horizontal_m"] > sem["sigma_horizontal_m"] + 0.05


    def test_sem_sigma_nao_inventa_precisao(self):
        r = intersect_offset_lines(lines(), method="PA1")
        assert r["sigma_e_m"] is None and r["sigma_model"] is None
        assert any("não propagados" in w for w in r["warnings"])


    def test_metodo_obrigatorio(self):
        with self.assertRaisesRegex(ValueError, "PA1 ou PA2"):
            intersect_offset_lines(lines(), method="PB1")


    def test_lado_obrigatorio_com_afastamento(self):
        with self.assertRaisesRegex(ValueError, "lado"):
            intersect_offset_lines(lines(side1=None), method="PA1")


    def test_retas_quase_paralelas(self):
        data = lines()
        data[1]["points"] = [P("p3", 500000, 100050), P("p4", 500100, 100051)]
        with self.assertRaisesRegex(ValueError, "quase paralelas"):
            intersect_offset_lines(data, method="PA1")


    def test_geograficas_com_sirgas_confirmado(self):
        r = intersect_offset_lines(lines(), method="PA1", utm_zone=22, hemisphere="N", sirgas2000_confirmed=True)
        assert -54 < r["longitude"] < -48 and 0 < r["latitude"] < 2
