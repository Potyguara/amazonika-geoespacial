"""Testes unitários para bloquear liberação automática de PS4."""
import unittest

from app.services.ps4_validation import (
    PS4Evidence, PS4Submission, PS4Vertex, evaluate_ps4,
)


def evidence(**kwargs):
    values = dict(
        scene_id="CENA-01", report_scene_id="CENA-01",
        raster_sha256="a" * 64, report_sha256="b" * 64,
        orthorectification_rms_m=1.0,
        horizontal_positional_precision_m=2.0,
        gsd_m=1.0, scene_crs="EPSG:31982",
        feature_identifiable=True,
    )
    values.update(kwargs)
    return PS4Evidence(**values)


class PS4ValidationTests(unittest.TestCase):
    def test_nao_aplicavel(self):
        result = evaluate_ps4(PS4Submission(needs_additional_vertices=False))
        self.assertEqual(result["status"], "NOT_APPLICABLE")

    def test_sem_relatorio_bloqueado(self):
        result = evaluate_ps4(PS4Submission(
            needs_additional_vertices=True,
            vertices=[PS4Vertex(vertex_id="V1", limit_type="natural", feature_type="river")],
        ))
        self.assertEqual(result["status"], "BLOCKED")

    def test_natural_requer_revisao_rt(self):
        result = evaluate_ps4(PS4Submission(
            needs_additional_vertices=True, evidence=evidence(),
            vertices=[PS4Vertex(vertex_id="V1", limit_type="natural", feature_type="river")],
        ))
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertTrue(result["requires_rt_review"])

    def test_cerca_nao_permitida(self):
        result = evaluate_ps4(PS4Submission(
            needs_additional_vertices=True, evidence=evidence(),
            vertices=[PS4Vertex(vertex_id="V1", limit_type="artificial", feature_type="fence")],
        ))
        self.assertEqual(result["status"], "BLOCKED")

    def test_limite_incompativel(self):
        result = evaluate_ps4(PS4Submission(
            needs_additional_vertices=True, evidence=evidence(horizontal_positional_precision_m=3.1),
            vertices=[PS4Vertex(vertex_id="V1", limit_type="natural", feature_type="river")],
        ))
        self.assertEqual(result["status"], "BLOCKED")

    def test_cena_diferente(self):
        result = evaluate_ps4(PS4Submission(
            needs_additional_vertices=True, evidence=evidence(report_scene_id="OUTRA"),
            vertices=[PS4Vertex(vertex_id="V1", limit_type="natural", feature_type="river")],
        ))
        self.assertEqual(result["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
