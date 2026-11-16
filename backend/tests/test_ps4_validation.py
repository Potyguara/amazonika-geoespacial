"""Testes unitários para bloquear liberação automática de PS4."""
import unittest
from unittest.mock import patch
from uuid import uuid4

from app.services.ps4_validation import (
    PS4Evidence, PS4Submission, PS4Vertex, evaluate_ps4, evaluate_verified_ps4,
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
            vertices=[PS4Vertex(vertex_id="V1", longitude=-51.0, latitude=0.1, limit_type="natural", feature_type="river")],
        ))
        self.assertEqual(result["status"], "BLOCKED")

    def test_natural_requer_revisao_rt(self):
        result = evaluate_ps4(PS4Submission(
            needs_additional_vertices=True, evidence=evidence(),
            vertices=[PS4Vertex(vertex_id="V1", longitude=-51.0, latitude=0.1, limit_type="natural", feature_type="river")],
        ))
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertTrue(result["requires_rt_review"])

    def test_cerca_nao_permitida(self):
        result = evaluate_ps4(PS4Submission(
            needs_additional_vertices=True, evidence=evidence(),
            vertices=[PS4Vertex(vertex_id="V1", longitude=-51.0, latitude=0.1, limit_type="artificial", feature_type="fence")],
        ))
        self.assertEqual(result["status"], "BLOCKED")

    def test_limite_incompativel(self):
        result = evaluate_ps4(PS4Submission(
            needs_additional_vertices=True, evidence=evidence(horizontal_positional_precision_m=3.1),
            vertices=[PS4Vertex(vertex_id="V1", longitude=-51.0, latitude=0.1, limit_type="natural", feature_type="river")],
        ))
        self.assertEqual(result["status"], "BLOCKED")

    def test_cena_diferente(self):
        result = evaluate_ps4(PS4Submission(
            needs_additional_vertices=True, evidence=evidence(report_scene_id="OUTRA"),
            vertices=[PS4Vertex(vertex_id="V1", longitude=-51.0, latitude=0.1, limit_type="natural", feature_type="river")],
        ))
        self.assertEqual(result["status"], "BLOCKED")

    def test_somente_hash_digitado_nao_comprova_upload(self):
        submitted = PS4Submission(
            needs_additional_vertices=True, evidence=evidence(),
            vertices=[PS4Vertex(
                vertex_id="V1", longitude=-51.0, latitude=0.1, limit_type="natural", feature_type="river"
            )],
        )
        result = evaluate_verified_ps4(submitted, {}, uuid4(), uuid4())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("não corresponde" in x for x in result["blockers"]))

    def test_integridade_arquivos_ainda_exige_rt(self):
        submitted = PS4Submission(
            needs_additional_vertices=True, evidence=evidence(),
            vertices=[PS4Vertex(
                vertex_id="V1", longitude=-51.0, latitude=0.1, limit_type="natural", feature_type="river"
            )],
        )
        assets = {
            "raster": {
                "kind": "raster", "sha256": "a" * 64,
                "metadata": {"wgs84_extent": {
                    "type": "Polygon", "coordinates": [[
                        [-52, -1], [-50, -1], [-50, 1], [-52, 1], [-52, -1]
                    ]]
                }},
            },
            "report": {"kind": "report", "sha256": "b" * 64},
        }
        with patch("app.services.ps4_assets.exists_matching", return_value=True):
            result = evaluate_verified_ps4(
                submitted, assets, uuid4(), uuid4(),
            )
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertTrue(result["requires_rt_review"])


if __name__ == "__main__":
    unittest.main()
