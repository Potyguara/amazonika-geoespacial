"""Verificações NTGIR/MTGIR por vértice."""
import unittest

from app.services.normative_checks import check_vertices


def V(code, method, limit="LA2", s=0.02, h=10.0, sh=0.03):
    return {"sigef_vertex_code": code, "sigef_method": method, "boundary_type": limit,
            "sigma_lat_m": s, "sigma_lon_m": s, "sigma_h_m": sh, "ellipsoidal_height_m": h}


class NormativeChecksTest(unittest.TestCase):
    def test_conforming_vertices(self):
        errors, rows, _ = check_vertices([V("ABCD-M-0001", "PG1"), V("ABCD-V-0002", "PA1"), V("ABC-P-0003", "PG7")], "P1")
        self.assertEqual(errors, [])
        self.assertTrue(all(r["ok"] for r in rows))

    def test_precision_limits_by_limit_type(self):
        errors, rows, _ = check_vertices([V("ABCD-V-0001", "PA1", "LN1", s=0.5), V("ABCD-V-0002", "PA1", "LN1", s=0.5)], "P1")
        self.assertEqual(errors, [])  # σP 0,707 ≤ 3,00 (natural)
        errors, _, _ = check_vertices([V("ABCD-V-0001", "PA1", "LA2", s=0.5), V("ABCD-V-0002", "PA1", "LA2", s=0.5)], "P1")
        self.assertTrue(any("0,50" in e or "0.50" in e for e in errors))

    def test_vertex_closing_artificial_limit_is_alerted(self):
        # V2 fecha o segmento LA2 de V1 e abre um LN1: alerta, sem bloqueio.
        errors, rows, alerts = check_vertices([V("ABCD-V-0001", "PA1", "LA2", s=0.1), V("ABCD-V-0002", "PA1", "LN1", s=1.0)], "P1")
        self.assertEqual(rows[1]["precision_limit_m"], 3.0)
        self.assertEqual(errors, [])
        self.assertTrue(alerts)

    def test_method_vertex_type_table_7(self):
        errors, _, _ = check_vertices([V("ABCD-V-0001", "PT8"), V("ABCD-M-0002", "PA1")], "P1")
        self.assertTrue(any("PT8 não admite vértice tipo V" in e for e in errors))
        self.assertTrue(any("PA1 não admite vértice tipo M" in e for e in errors))

    def test_table_6_restrictions(self):
        errors, _, _ = check_vertices([V("ABCD-P-0001", "PG8", "LA2"), V("ABCD-V-0002", "PS4", "LA1")], "P1")
        self.assertTrue(any("só se aplica a limite natural" in e for e in errors))
        self.assertTrue(any("cerca" in e for e in errors))

    def test_missing_height_and_sigmas(self):
        errors, _, _ = check_vertices([V("ABCD-V-0001", "PA2", h=None, sh=None)], "P1")
        self.assertTrue(any("h ausente" in e for e in errors))
        self.assertTrue(any("obrigatórios" in e for e in errors))

    def test_code_format(self):
        errors, _, _ = check_vertices([V("ABCDEF-V-0001", "PA1")], "P1")
        self.assertTrue(any("NTGIR 3.3" in e for e in errors))

    def test_pa3_sigmas_zero(self):
        errors, _, _ = check_vertices([V("ABCD-V-0001", "PA3", s=0.1, sh=0.1)], "P1")
        self.assertTrue(any("PA3" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
