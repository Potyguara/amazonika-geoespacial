"""Regressões: destaque, fluxo de texto e confrontações prioritárias."""
import io
import unittest
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.pagesizes import A4
from pypdf import PdfReader

from app.services.plant_memorial_professional import (
    _para, _highlight_memorial_text, _remove_redundant_auto_header,
)
from app.services.plant_detail_elements import grouped_label_positions


class MemorialManualRegressionTests(unittest.TestCase):
    def test_highlights_confrontant_and_original_vertex(self):
        marked=_highlight_memorial_text(
            "Segue com Ramal São Benedito do Aporema até EQGV-M-0305.",
            ["Ramal São Benedito do Aporema"],
        )
        self.assertIn("<b>Ramal São Benedito do Aporema</b>",marked)
        self.assertIn("<b>EQGV-M-0305</b>",marked)
        self.assertTrue(_para(marked,justify=True).style.alignment==4)

    def test_untrusted_markup_remains_escaped(self):
        marked=_highlight_memorial_text(
            "Vértice EQGV-V-502 <script>e confronto X</script>",
            ["X"],
        )
        self.assertNotIn("<script>",marked)
        self.assertIn("&lt;script&gt;",marked)

    def test_only_default_prologue_is_trimmed(self):
        original=(
            "MEMORIAL DESCRITIVO\nRETIRO NOVA VIDA I\n"
            "IMÓVEL: RETIRO NOVA VIDA I\n"
            "DESCRIÇÃO DO PERÍMETRO - RETIRO NOVA VIDA I\n"
            "Inicia-se a descrição do perímetro no vértice EQGV-V-502."
        )
        result=_remove_redundant_auto_header(original)
        self.assertTrue(result.startswith("Inicia-se a descrição"))
        custom="MEMORIAL DE AUTORIA TÉCNICA\nTexto revisado"
        self.assertEqual(_remove_redundant_auto_header(custom),custom)

    def test_paragraph_renders_with_emphasis_and_justification(self):
        pdf_bytes=io.BytesIO()
        pdf=Canvas(pdf_bytes,pagesize=A4)
        marked=_highlight_memorial_text(
            "Deste segue confrontando com Vizinhança Teste até EQGV-V-502.",
            ["Vizinhança Teste"]
        )
        paragraph=_para(marked,justify=True)
        _,h=paragraph.wrap(350,400)
        paragraph.drawOn(pdf,40,740-h)
        pdf.save()
        txt=PdfReader(io.BytesIO(pdf_bytes.getvalue())).pages[0].extract_text()
        self.assertIn("EQGV-V-502",txt)
        self.assertIn("Vizinhança Teste",txt)


if __name__=="__main__":
    unittest.main()
