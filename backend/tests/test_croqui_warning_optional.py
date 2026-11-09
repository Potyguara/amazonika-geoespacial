"""Regressões do controle de ressalva opcional de croqui."""
import io
import unittest

from pypdf import PdfReader

from app.services.plant_croqui_warning import (
    LEGACY_PRECISION_NOTICE,
    PROFESSIONAL_PRECISION_NOTICE,
    remove_optional_warnings,
)
from app.services.plant_memorial_v2 import DISCLAIMER, build_joint_memorial
from app.services.plant_memorial_v3 import make_joint_pdf
from test_final_paper_formats import small_property, FLAGS


class OptionalCroquiWarningTests(unittest.TestCase):
    def test_old_edited_draft_is_cleaned_when_unchecked(self):
        old = (
            "Descrição técnica aprovada.\n\n" + LEGACY_PRECISION_NOTICE
            + "\n\nOBSERVAÇÃO:\n" + DISCLAIMER
            + "\n\nObservação particular: estrada vicinal."
        )
        clean = remove_optional_warnings(old, False)
        self.assertIn("Descrição técnica aprovada", clean)
        self.assertIn("Observação particular: estrada vicinal", clean)
        self.assertNotIn("OBSERVAÇÃO:", clean)
        self.assertNotIn("coordenadas precisas", clean)
        self.assertNotIn("certificação fundiária", clean)

    def test_checked_preserves_legacy_notice(self):
        old = "Texto existente.\nOBSERVAÇÃO:\n" + DISCLAIMER
        self.assertEqual(remove_optional_warnings(old, True),old)
        self.assertEqual(remove_optional_warnings(None,False),None)

    def test_draft_from_service_does_not_include_warning_when_unchecked(self):
        text=build_joint_memorial(
            small_property(), title="LOTE PEQUENO",
            owner="DETENTOR",responsible="TÉCNICO",croqui=False,
        )
        self.assertNotIn("Este documento se trata apenas de um croqui",text)
        self.assertNotIn("A precisão depende",text)

    def test_real_pdf_false_without_edited_memorial(self):
        self._check_pdf(False,None,expected=False)

    def test_real_pdf_false_with_stale_edited_memorial(self):
        old = (
            "Inicia-se a descrição deste perímetro em EQGV-M-001."
            + "\n\n" + PROFESSIONAL_PRECISION_NOTICE
            + "\n\nOBSERVAÇÃO:\n" + DISCLAIMER
        )
        self._check_pdf(False,old,expected=False)

    def test_real_pdf_true_renders_optional_notice(self):
        self._check_pdf(True,None,expected=True)

    def _check_pdf(self,croqui,edited,expected):
        data,paper,scale=make_joint_pdf(
            parcels=small_property(),title="LOTE PEQUENO",
            owner_name="DETENTOR",owner_cpf="000.000.000-00",
            responsible_name="TÉCNICO",
            professional={"full_name":"TÉCNICO","crea":"CREA 1"},
            croqui=croqui,raster_b64=None,raster_source=None,
            paper_format="A4",orientation="retrato",
            layout_template="classic_lateral",
            plant_elements=FLAGS,
            edited_memorial=edited,
        )
        reader=PdfReader(io.BytesIO(data))
        text="\n".join(page.extract_text() or "" for page in reader.pages)
        self.assertEqual("Este documento se trata apenas de um croqui" in text,expected)
        if not expected:
            self.assertNotIn("A precisão depende",text)
            self.assertNotIn("OBSERVAÇÃO:",text)


if __name__=="__main__":
    unittest.main()
