import unittest
from app.services.ps4_planimetric_check import evaluate_checkpoints

METADATA = {"crs_authority": "EPSG:32622"}

def checkpoint(name, lon, lat, shift=0):
    return {"name": name, "gnss_longitude": lon, "gnss_latitude": lat,
            "image_longitude": lon + shift, "image_latitude": lat,
            "used_for_orthorectification": False}

class PlanimetricCheckTests(unittest.TestCase):
    def test_sem_controles_nao_aprova(self):
        r = evaluate_checkpoints([], METADATA)
        self.assertEqual(r["status"], "NO_CHECKPOINTS")
        self.assertIsNone(r["rms_horizontal_m"])

    def test_deslocamento_real_um_ponto_insuficiente(self):
        r = evaluate_checkpoints([checkpoint("M-1", -50.87, 0.4, 0.00001)], METADATA)
        self.assertEqual(r["status"], "INSUFFICIENT_CHECKPOINTS")
        self.assertGreater(r["rms_horizontal_m"], 0.5)
        self.assertLess(r["rms_horizontal_m"], 2)
        self.assertEqual(r["count"], 1)

    def test_ponto_usado_na_ortorretificacao_rejeitado(self):
        point = checkpoint("M-1", -50.87, 0.4)
        point["used_for_orthorectification"] = True
        with self.assertRaisesRegex(ValueError, "não é checagem independente"):
            evaluate_checkpoints([point], METADATA)

    def test_pontos_repetidos_rejeitados(self):
        a = checkpoint("M-1", -50.87, 0.4)
        with self.assertRaisesRegex(ValueError, "repetido"):
            evaluate_checkpoints([a,a], METADATA)

    def test_crs_geografico_rejeitado(self):
        with self.assertRaisesRegex(ValueError, "planas métricas"):
            evaluate_checkpoints([checkpoint("M-1", -50.87, 0.4)],
                                 {"crs_authority": "EPSG:4326"})

if __name__ == "__main__":
    unittest.main()
