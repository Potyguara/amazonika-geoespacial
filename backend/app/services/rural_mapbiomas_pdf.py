"""Preliminary in-memory MapBiomas PDF with class-area bars and provenance."""
from datetime import datetime
from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


def _fmt(value, decimals=4):
    return f"{float(value):,.{decimals}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _safe(text, length=250):
    return escape(str(text if text is not None else "Não informado")[:length])


def mapbiomas_pdf(*, property_name: str, cadastral_source: str,
                  cadastral_code: str | None, report: dict,
                  generated_at: datetime) -> bytes:
    if report.get("status") != "ANALYZED" or not report.get("classes"):
        raise ValueError("Estatísticas MapBiomas ausentes ou incompletas.")
    stream = BytesIO()
    doc = SimpleDocTemplate(
        stream, pagesize=A4, leftMargin=19 * mm, rightMargin=19 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
        pageCompression=1,
        title="Amazonika - Prévia de uso e cobertura do solo",
        author="Amazonika Geoespacial",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="AKTitle", parent=styles["Heading1"], fontName="Helvetica-Bold",
        fontSize=18, leading=23, textColor=colors.HexColor("#174D37"), spaceAfter=11,
    ))
    styles.add(ParagraphStyle(
        name="AKBody", parent=styles["BodyText"], fontSize=9, leading=14,
        textColor=colors.HexColor("#25483A"), spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="AKSmall", parent=styles["BodyText"], fontSize=8, leading=11,
        textColor=colors.HexColor("#576C60"), spaceAfter=4,
    ))
    story = [
        Paragraph("AMAZONIKA GEOESPACIAL", styles["AKSmall"]),
        Spacer(1, 3 * mm),
        Paragraph("Uso e cobertura do solo — MapBiomas", styles["AKTitle"]),
        Paragraph(
            "PRÉVIA NÃO CERTIFICADA. Estimativas por sensoriamento remoto. "
            "Não comprova domínio, regularidade ambiental ou ausência de infrações.",
            styles["AKSmall"],
        ),
        Spacer(1, 4 * mm),
        Paragraph("1. Identificação e origem dos dados", styles["Heading2"]),
    ]
    for label, value in [
        ("Imóvel", property_name),
        ("Fonte cadastral", cadastral_source),
        ("Código", cadastral_code or "Não informado"),
        ("Produto", f"MapBiomas Brasil — Coleção {report['collection']}"),
        ("Ano", str(report["year"])),
        ("Resolução nominal", str(report["resolution_m"]) + " metros"),
        ("Área geométrica", _fmt(report["geometry_area_hectares"]) + " ha"),
        ("Área com classificação", _fmt(report["classified_area_hectares"]) + " ha"),
        ("Data/hora da emissão", generated_at.strftime("%d/%m/%Y %H:%M UTC")),
    ]:
        story.append(Paragraph(f"<b>{_safe(label)}:</b> {_safe(value)}", styles["AKBody"]))

    story.append(Paragraph("2. Distribuição das classes", styles["Heading2"]))
    rows = [[
        Paragraph("<b>Classe</b>", styles["AKBody"]),
        Paragraph("<b>Área (ha)</b>", styles["AKBody"]),
        Paragraph("<b>% classificado</b>", styles["AKBody"]),
    ]]
    for item in report["classes"]:
        rows.append([
            Paragraph(_safe(f"{item['code']} — {item['name']}"), styles["AKBody"]),
            _fmt(item["area_hectares"]),
            _fmt(item["percent_classified"], 2) + "%",
        ])
    tbl = Table(rows, colWidths=[108*mm, 30*mm, 34*mm], repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8F2EB")),
        ("LINEBELOW", (0, 0), (-1, -1), .25, colors.HexColor("#D9E5DC")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F6F9F7")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("3. Metodologia, fontes e limitações", styles["Heading2"]))
    story.append(Paragraph(_safe(report.get("method"), 550), styles["AKBody"]))
    story.append(Paragraph(f"<b>Asset:</b> {_safe(report['asset_id'], 210)}", styles["AKSmall"]))
    story.append(Paragraph(
        f"<b>Consulta remota:</b> {_safe(report.get('queried_at'))}", styles["AKSmall"]))
    story.append(Paragraph(_safe(report.get("warning"), 550), styles["AKSmall"]))
    story.append(Paragraph(
        "A distribuição de classes é estimada em resolução raster de 30 metros. "
        "Totais de pixels classificados podem diferir da área do perímetro por "
        "bordas, máscaras e resolução. Classes não mapeadas nominalmente devem "
        "ser conferidas na legenda oficial da Coleção 11. "
        "Documento preliminar sem assinatura técnica ou QR de autenticidade.",
        styles["AKSmall"],
    ))

    def footer(canvas, report_doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#62776A"))
        canvas.drawString(19*mm, 12*mm, "Amazonika Geoespacial - prévia de uso do solo")
        canvas.drawRightString(A4[0]-19*mm, 12*mm, f"Página {report_doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    output = stream.getvalue()
    if not output.startswith(b"%PDF") or len(output) > 8 * 1024 * 1024:
        raise ValueError("PDF de uso do solo inválido ou excedeu limite.")
    return output
