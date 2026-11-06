"""Preliminary in-memory MapBiomas PDF with class-area bars and provenance."""
from datetime import datetime
from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Flowable, PageBreak, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.utils import ImageReader
from pyproj import Geod
from app.services.rural_mapbiomas_cartography import ThematicThumbnail
import math


def _fmt(value, decimals=4):
    return f"{float(value):,.{decimals}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _safe(text, length=250):
    return escape(str(text if text is not None else "Não informado")[:length])


class MapBiomasClassBars(Flowable):
    """Charts class area shares only; NOT a georeferenced thematic map."""

    def __init__(self, classes: list[dict], width: float = 168 * mm):
        super().__init__()
        self.classes = classes[:20]
        self.width = width
        self.height = 10 * mm + len(self.classes) * 7.5 * mm

    def draw(self):
        c = self.canv
        c.setFont("Helvetica", 7)
        for index, item in enumerate(self.classes):
            y = self.height - 8 * mm - index * 7.5 * mm
            name = f"{item['code']} — {str(item['name'])[:32]}"
            c.setFillColor(colors.HexColor("#203D32"))
            c.drawString(0, y + 1, name)
            left = 82 * mm
            bar_width = 70 * mm
            c.setFillColor(colors.HexColor("#E9EFEA"))
            c.roundRect(left, y - 1, bar_width, 4 * mm, 1, stroke=0, fill=1)
            share = max(0.0, min(100.0, float(item['percent_classified'])))
            color = item.get("color") or "#8D9A94"
            try:
                fill = colors.HexColor(color)
            except (TypeError, ValueError):
                fill = colors.HexColor("#8D9A94")
            c.setFillColor(fill)
            if share > 0:
                c.roundRect(left, y - 1, bar_width * share / 100, 4 * mm,
                            1, stroke=0, fill=1)
            c.setFillColor(colors.HexColor("#203D32"))
            c.drawRightString(self.width, y + 1, _fmt(share, 2) + "%")


class MapBiomasThematicMap(Flowable):
    """Rendered official pixel thumbnail; WGS84 extent gives approximate scale."""

    def __init__(self, thumb: ThematicThumbnail, class_rows: list[dict]):
        super().__init__()
        self.thumb = thumb
        self.class_rows = class_rows
        self.width = 170 * mm
        self.height = 173 * mm

    def draw(self):
        c = self.canv
        c.setStrokeColor(colors.HexColor("#CBDDD0"))
        c.setFillColor(colors.white)
        c.roundRect(0, 0, self.width, self.height, 5, stroke=1, fill=1)
        # Never stretch a pixel grid independently of its width-to-height ratio.
        px_ratio = self.thumb.width / self.thumb.height
        max_width, max_height = 155 * mm, 129 * mm
        display_w = min(max_width, max_height * px_ratio)
        display_h = display_w / px_ratio
        x = (self.width - display_w) / 2
        y = 24 * mm + (max_height - display_h) / 2
        c.drawImage(
            ImageReader(BytesIO(self.thumb.png)), x, y,
            width=display_w, height=display_h, mask="auto",
        )
        c.setStrokeColor(colors.HexColor("#355244"))
        c.rect(x, y, display_w, display_h, stroke=1, fill=0)
        c.setFillColor(colors.HexColor("#203D32"))
        c.setFont("Helvetica-Bold", 8)
        c.drawString(7 * mm, self.height - 7 * mm,
                     f"Classes MapBiomas {self.thumb.year} — pixels reais do imóvel")
        # North is geographic grid-up under the EPSG:4326 thumbnail request.
        c.setStrokeColor(colors.HexColor("#203D32"))
        c.setLineWidth(1.2)
        arrow_x, arrow_y = self.width - 12 * mm, self.height - 21 * mm
        c.line(arrow_x, arrow_y - 8 * mm, arrow_x, arrow_y)
        p = c.beginPath()
        p.moveTo(arrow_x, arrow_y + 4 * mm)
        p.lineTo(arrow_x - 2.5 * mm, arrow_y - 2 * mm)
        p.lineTo(arrow_x + 2.5 * mm, arrow_y - 2 * mm)
        p.close()
        c.drawPath(p, fill=1, stroke=0)
        c.drawCentredString(arrow_x, arrow_y + 6 * mm, "N")

        # Estimate ground distance from geographic longitude along centerline,
        # not a survey-grade projected-coordinate scale bar.
        west, south, east, north = self.thumb.bounds
        middle = (south + north) / 2
        _, _, width_m = Geod(ellps="GRS80").inv(west, middle, east, middle)
        if width_m > 0:
            bar_meters = 10 ** math.floor(math.log10(width_m * .3))
            for unit in (5, 2, 1):
                if bar_meters * unit <= width_m * .35:
                    bar_meters *= unit
                    break
            bar_w = display_w * bar_meters / width_m
            c.setFillColor(colors.HexColor("#203D32"))
            c.rect(x, 13 * mm, bar_w, 2 * mm, stroke=0, fill=1)
            c.setFont("Helvetica", 7)
            c.drawString(x, 17 * mm, f"Escala gráfica aproximada: {bar_meters / 1000:g} km"
                         if bar_meters >= 1000 else
                         f"Escala gráfica aproximada: {bar_meters:g} m")
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.HexColor("#53685D"))
        c.drawString(7 * mm, 5 * mm,
                     "Visualização raster recortada ao CAR; não substitui planta georreferenciada.")


def mapbiomas_pdf(*, property_name: str, cadastral_source: str,
                  cadastral_code: str | None, report: dict,
                  generated_at: datetime,
                  thematic_map: ThematicThumbnail | None = None) -> bytes:
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
    # Prevent an orphan heading on page 1 while all class bars flow to page 2.
    # This chart and its explanation are one semantic block.
    story.append(KeepTogether([
        Spacer(1, 4 * mm),
        Paragraph("3. Participação por classe", styles["Heading2"]),
        MapBiomasClassBars(report["classes"]),
        Paragraph(
            "Gráfico de participação relativa da área classificada. "
            "Não representa a posição espacial dos pixels e não substitui "
            "o mapa temático georreferenciado.",
            styles["AKSmall"],
        ),
    ]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("4. Metodologia, fontes e limitações", styles["Heading2"]))
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

    if thematic_map is not None:
        story.append(PageBreak())
        story.append(Paragraph("5. Mapa temático do uso e cobertura do solo", styles["AKTitle"]))
        story.append(Paragraph(
            "Imagem temática gerada com pixels reais da classificação MapBiomas, "
            "recortados ao perímetro cadastral consultado. A distribuição por "
            "classe é espacial e diferente do gráfico de participação.",
            styles["AKSmall"],
        ))
        story.append(MapBiomasThematicMap(thematic_map, report["classes"]))
        legend_rows = []
        for item in report["classes"]:
            code = item["code"]
            if code not in thematic_map.class_codes:
                continue
            col = item.get("color") or "#8D9A94"
            legend_rows.append([
                Paragraph(f'<font color="{col}">&#9632;</font>  '
                          + _safe(f'{code} — {item["name"]}'), styles["AKSmall"]),
                _fmt(item["area_hectares"]) + " ha",
            ])
        if legend_rows:
            legend = Table(legend_rows, colWidths=[135 * mm, 35 * mm])
            legend.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1),
                 [colors.white, colors.HexColor("#F6F9F7")]),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(legend)
        story.append(Paragraph(
            "Fonte: MapBiomas Brasil, Coleção 11, ano "
            + str(thematic_map.year) +
            ". Miniatura cartográfica para triagem ambiental; "
            "não usar para delimitar APP, RL ou áreas a suprimir.",
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
