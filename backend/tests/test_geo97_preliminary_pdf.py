"""Testes isolados GEO97: sem dependência de rede, banco ou credenciais."""
from io import BytesIO
import unittest

from reportlab.pdfgen import canvas
from pypdf import PdfReader

from app.services.preliminary_pdf_stamp import stamp_preliminary_pdf


class PreliminaryDocumentTest(unittest.TestCase):
    def test_preliminary_watermark_on_all_pages(self):
        output = BytesIO()
        doc = canvas.Canvas(output, pagesize=(595,842))
        for idx in range(2):
            doc.drawString(40,700,"Pagina "+str(idx+1))
            doc.showPage()
        doc.save()
        stamped = stamp_preliminary_pdf(output.getvalue())
        result = PdfReader(BytesIO(stamped))
        self.assertEqual(len(result.pages),2)
        for page in result.pages:
            self.assertIn("PRELIMINAR - NAO CERTIFICADA",page.extract_text())


if __name__ == "__main__":
    unittest.main()
