"""Marca de segurança em PDFs de perímetro PS4 não certificado."""
from io import BytesIO

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.pdfgen import canvas


def stamp_preliminary_pdf(raw_pdf: bytes) -> bytes:
    reader = PdfReader(BytesIO(raw_pdf))
    writer = PdfWriter()
    for page in reader.pages:
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        buffer = BytesIO()
        overlay = canvas.Canvas(buffer, pagesize=(w, h))
        overlay.saveState()
        overlay.translate(w / 2, h / 2)
        overlay.rotate(34)
        overlay.setFillColor(colors.Color(0.62, 0.18, 0.12, alpha=0.13))
        overlay.setFont("Helvetica-Bold", min(52, max(18, w / 24)))
        overlay.drawCentredString(0, 0, "PRELIMINAR - NAO CERTIFICADA")
        overlay.restoreState()
        overlay.setFillColor(colors.HexColor("#8f3225"))
        overlay.setFont("Helvetica-Bold", 8)
        overlay.drawCentredString(
            w / 2, 13,
            "DOCUMENTO PRELIMINAR - SUJEITO A REVISAO TECNICA PARA SIGEF",
        )
        overlay.setFont("Helvetica", 7)
        overlay.drawCentredString(
            w / 2, 25,
            "HN~ = altitude normal estimada; consultar a metodologia. HN nao substitui h SIGEF.",
        )
        overlay.save()
        buffer.seek(0)
        stamp_page = PdfReader(buffer).pages[0]
        page.merge_page(stamp_page)
        writer.add_page(page)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
