import unittest
from app.services.ps1_accuracy import evaluate_ps1_checkpoints, ps1_height


class PS1AccuracyTest(unittest.TestCase):
    def rows(self):
        return [
            {"id": "A", "used_for_control": False, "delta_e_m": .1, "delta_n_m": .2, "delta_h_m": .3},
            {"id": "B", "used_for_control": False, "delta_e_m": -.1, "delta_n_m": -.2, "delta_h_m": -.3},
        ]

    def test_rms(self):
        r = evaluate_ps1_checkpoints(self.rows(), "ARTIFICIAL")
        self.assertAlmostEqual(r["sigma_e_m"], .1)
        self.assertAlmostEqual(r["sigma_n_m"], .2)
        self.assertAlmostEqual(r["sigma_h_m"], .3)
        self.assertTrue(r["within_horizontal_limit"])
        self.assertFalse(r["ready_for_sigef"])

    def test_control_rejected(self):
        rows = self.rows()
        rows[0]["used_for_control"] = True
        with self.assertRaises(ValueError):
            evaluate_ps1_checkpoints(rows, "NATURAL")

    def test_duplicate_rejected(self):
        rows = self.rows()
        rows[1]["id"] = "A"
        with self.assertRaises(ValueError):
            evaluate_ps1_checkpoints(rows, "NATURAL")

    def test_limit(self):
        rows = self.rows()
        rows[0]["delta_e_m"] = 4
        self.assertFalse(evaluate_ps1_checkpoints(rows, "ARTIFICIAL")["within_horizontal_limit"])

    def test_normal_height(self):
        r = ps1_height(100, .3, kind="NORMAL", factor=-10, factor_sigma=.4)
        self.assertAlmostEqual(r["ellipsoidal_height_m"], 90)
        self.assertAlmostEqual(r["sigma_h_m"], .5)

    def test_missing_conversion(self):
        with self.assertRaises(ValueError):
            ps1_height(100, .3, kind="NORMAL")

    def test_ellipsoidal(self):
        self.assertEqual(ps1_height(90, .3, kind="ELLIPSOIDAL")["ellipsoidal_height_m"], 90)

    def test_nonfinite(self):
        with self.assertRaises(ValueError):
            ps1_height(float("nan"), .3, kind="ELLIPSOIDAL")
