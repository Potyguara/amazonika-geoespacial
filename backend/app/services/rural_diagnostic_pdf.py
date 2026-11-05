"""In-memory PDF for a preliminary rural environmental diagnosis.

This document is NOT a cadastral certificate, a compliance finding or an
official issuance. No raster national bases or PDF are persisted to disk.
The server recomputes WFS results for the selected official monitoring layer.
"""
from __future__ import annotations

from datetime import datetime
from html import escape
from io import BytesIO
from math import cos, radians

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)
from shapely.geometry import shape

GREEN = colors.HexColor("#174D37")
DARK = colors.HexColor("#213D33")
MUTED = colors.HexColor("#566B62")
LINE = colors.HexColor("#D7E4DB")
PALE = colors.HexColor("#EAF4EC")
RED = colors.HexColor("#C54A3B")
LIGHT_RED = colors.HexColor("#FBE1DC")
MAX_FEATURE_ROWS = 80


def _fmt(value: float | int | None, places: int = 4) -> str:
    if value is None:
        return "Não informado"
    return f"{float(value):,.{places}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _clean(value: object, max_chars: int = 240) -> str:
    return escape(str(value if value is not None else "Não informado")[:max_chars])


class RuralIntersectionMap(Flowable):
    """Vector sketch in geographic coordinates, not a survey-grade plan."""

    def __init__(self, subject_geometry: dict, results: list[dict], width: float = 176 * mm):
        super().__init__()
        self.width = width
        self.height = 108 * mm
        self.subject = shape(subject_geometry)
        self.overlaps = []
        for item in results:
            geometry = item.get("intersection_geometry")
            if geometry:
                try:
                    self.overlaps.append(shape(geometry))
                except (TypeError, ValueError):
                    pass

    def draw(self):
        c = self.canv
        width, height = self.width, self.height
        c.setFillColor(colors.white)
        c.setStrokeColor(LINE)
        c.rect(0, 0, width, height, fill=1, stroke=1)

        # Project latitude approximately into metric-like map units for visual
        # proportions; not a legally valid measured map.
        minx, miny, maxx, maxy = self.subject.bounds
        lat_mid = (miny + maxy) / 2.0
        lon_factor = max(0.1, abs(cos(radians(lat_mid))))
        x_span = max((maxx - minx) * lon_factor, 0.000001)
        y_span = max(maxy - miny, 0.000001)
        scale = min((width - 28) / x_span, (height - 28) / y_span)
        origin_x = (width - x_span * scale) / 2
        origin_y = (height - y_span * scale) / 2

        def xy(lon, lat):
            return (
                origin_x + (lon - minx) * lon_factor * scale,
                origin_y + (lat - miny) * scale,
            )

        def draw_polygons(geometry, fill, stroke, line_width):
            if geometry.geom_type == "Polygon":
                parts = [geometry]
            elif geometry.geom_type == "MultiPolygon":
                parts = list(geometry.geoms)
            elif geometry.geom_type == "GeometryCollection":
                for part in geometry.geoms:
                    draw_polygons(part, fill, stroke, line_width)
                return
            else:
                return
            for polygon in parts:
                # Only simplify the map representation; numerical calculations
                # use the unsimplified WFS intersections.
                tolerance = max(maxx - minx, maxy - miny) / 3000
                visual = polygon.simplify(tolerance, preserve_topology=True)
                c.setStrokeColor(stroke)
                c.setFillColor(fill)
                c.setLineWidth(line_width)
                path = c.beginPath()
                for index, (lon, lat) in enumerate(visual.exterior.coords):
                    x, y = xy(lon, lat)
                    if index == 0:
                        path.moveTo(x, y)
                    else:
                        path.lineTo(x, y)
                path.close()
                for inner in visual.interiors:
                    for index, (lon, lat) in enumerate(inner.coords):
                        x, y = xy(lon, lat)
                        if index == 0:
                            path.moveTo(x, y)
                        else:
                            path.lineTo(x, y)
                    path.close()
                c.drawPath(path, stroke=1, fill=1, fillMode=0)

        draw_polygons(self.subject, PALE, GREEN, 1.4)
        for intersection in self.overlaps:
            draw_polygons(intersection, LIGHT_RED, RED, 1.4)

        c.setFont("Helvetica", 8)
        c.setFillColor(DARK)
        c.drawString(7, height - 11, "Esquema de interseções - geometrias oficiais da consulta")
        c.setFont("Helvetica", 7)
        c.drawString(8, 7, "Verde: perímetro consultado")
        c.setFillColor(RED)
        c.drawString(width - 158, 7, "Vermelho: interseções PRODES/DETER")


def build_rural_monitoring_pdf(
    *,
    property_name: str,
    property_source: str,
    cadastral_code: str | None,
    subject_geometry: dict,
    monitoring: dict,
    generated_at: datetime,
) -> bytes:
    """Render a standalone provisional technical PDF from server-side results."""
    if monitoring.get("status") != "ANALYZED":
        raise ValueError("Não é permitido gerar relatório de consulta incompleta.")
    from app.services.rural_monitoring import _feature_area_ha

    subject = shape(subject_geometry)
    if subject.is_empty or not subject.is_valid or subject.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("Perímetro inválido para o relatório rural.")
    property_ha = _feature_area_ha(subject)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=17 * mm, leftMargin=17 * mm,
        topMargin=20 * mm, bottomMargin=19 * mm,
        title="Prévia de Diagnóstico Ambiental Rural - Amazonika",
        author="Amazonika Geoespacial",
        pageCompression=1,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="AmazonikaTitle", parent=styles["Heading1"], fontName="Helvetica-Bold",
        fontSize=19, leading=24, textColor=GREEN, spaceAfter=9,
    ))
    styles.add(ParagraphStyle(
        name="AmazonikaSub", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=11.5, leading=15, textColor=DARK, spaceBefore=13, spaceAfter=7,
    ))
    styles.add(ParagraphStyle(
        name="AmazonikaSmall", parent=styles["BodyText"],
        fontName="Helvetica", fontSize=8, leading=12, textColor=DARK,
    ))
    styles.add(ParagraphStyle(
        name="AmazonikaMuted", parent=styles["BodyText"],
        fontName="Helvetica", fontSize=8, leading=11, textColor=MUTED,
    ))
    styles.add(ParagraphStyle(
        name="AmazonikaTable", parent=styles["BodyText"],
        fontName="Helvetica", fontSize=7.4, leading=10, textColor=DARK,
    ))

    story = [
        Paragraph("AMAZONIKA GEOESPACIAL", styles["AmazonikaMuted"]),
        Spacer(1, 4 * mm),
        Paragraph("Prévia de Diagnóstico Ambiental Rural", styles["AmazonikaTitle"]),
        Paragraph(
            "DOCUMENTO PRELIMINAR - consulta geoespacial pública sob demanda. "
            "Não é laudo pericial, certidão CAR, comprovação de domínio ou "
            "declaração de regularidade ambiental.",
            styles["AmazonikaMuted"],
        ),
        Spacer(1, 6 * mm),
        Paragraph("1. Identificação do imóvel", styles["AmazonikaSub"]),
    ]

    fields = [
        ("Imóvel / identificação", property_name),
        ("Origem do perímetro", property_source),
        ("Código cadastral", cadastral_code or "Não informado"),
        ("Área geométrica aproximada", _fmt(property_ha) + " ha"),
        ("Consulta emitida em UTC", generated_at.strftime("%d/%m/%Y %H:%M UTC")),
    ]
    for label, value in fields:
        story.append(Paragraph(
            f"<b>{_clean(label)}:</b> {_clean(value)}", styles["AmazonikaSmall"]
        ))

    story += [
        Paragraph("2. Indicadores oficiais de monitoramento", styles["AmazonikaSub"]),
        Paragraph(
            f"<b>Programa:</b> {_clean(monitoring.get('program'))} | "
            f"<b>Camada:</b> {_clean(monitoring.get('layer_title'))} "
            f"({_clean(monitoring.get('layer'))})",
            styles["AmazonikaSmall"],
        ),
    ]
    summary = [
        ["Feições interferentes", "Área de interseção única", "Percentual do imóvel"],
        [
            str(monitoring.get("interfering_features", 0)),
            _fmt(monitoring.get("overlap_hectares")) + " ha",
            _fmt(monitoring.get("overlap_percent"), 2) + "%",
        ],
    ]
    tbl = Table(summary, colWidths=[52 * mm, 65 * mm, 59 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 1), (-1, 1), PALE),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    story.extend([Spacer(1, 5 * mm), tbl])

    story.append(Paragraph("3. Mapa esquemático das interseções", styles["AmazonikaSub"]))
    story.append(RuralIntersectionMap(subject_geometry, monitoring.get("features") or []))
    story.append(Paragraph(
        "Representação simplificada para visualização. Distâncias, coordenadas "
        "e áreas são calculadas com os dados originais, não a partir deste desenho.",
        styles["AmazonikaMuted"],
    ))
    story.append(Paragraph("4. Feições identificadas", styles["AmazonikaSub"]))
    features = monitoring.get("features") or []
    if not features:
        story.append(Paragraph(
            "Nenhuma interferência geométrica encontrada na camada consultada. "
            "Este resultado não significa ausência de desmatamento ou de restrições.",
            styles["AmazonikaSmall"],
        ))
    else:
        rows = [["Nº", "Identificador WFS", "Área de interseção (ha)", "Atributos publicados"]]
        for index, feat in enumerate(features[:MAX_FEATURE_ROWS], 1):
            attrs = feat.get("attributes") or {}
            text_attrs = "; ".join(
                f"{key}: {str(value)}" for key, value in list(attrs.items())[:8]
            )
            rows.append([
                str(index),
                Paragraph(_clean(feat.get("id") or "Sem ID", 100), styles["AmazonikaTable"]),
                _fmt(feat.get("overlap_hectares")),
                Paragraph(_clean(text_attrs or "Sem atributos adicionais", 400), styles["AmazonikaTable"]),
            ])
        detailed = Table(
            rows, colWidths=[10 * mm, 40 * mm, 32 * mm, 94 * mm],
            repeatRows=1, hAlign="LEFT",
        )
        detailed.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), GREEN),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
            ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(detailed)
        if len(features) > MAX_FEATURE_ROWS:
            story.append(Paragraph(
                f"Detalhamento visual restrito às primeiras {MAX_FEATURE_ROWS} "
                f"de {len(features)} feições. Os indicadores consolidados consideram todas.",
                styles["AmazonikaMuted"],
            ))

    story.append(Paragraph("5. Metodologia e limitações", styles["AmazonikaSub"]))
    story.append(Paragraph(_clean(monitoring.get("method") or "WFS e interseção geodésica."), styles["AmazonikaSmall"]))
    story.append(Paragraph(f"<b>Serviço consultado:</b> {_clean(monitoring.get('service_url'))}",
                           styles["AmazonikaSmall"]))
    story.append(Paragraph(
        f"<b>Momento da consulta dos dados:</b> {_clean(monitoring.get('queried_at'))}",
        styles["AmazonikaSmall"],
    ))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(_clean(monitoring.get("warning") or
                                  "A camada selecionada não comprova infração."), styles["AmazonikaMuted"]))
    story.append(Paragraph(
        "A consulta foi realizada sobre uma camada e sua cobertura específica. "
        "Outras bases e períodos não foram avaliados neste documento. "
        "Eventual ausência de feições não constitui certificado de inexistência "
        "de desmatamento. Para diagnóstico completo, avaliar todas as fontes pertinentes.",
        styles["AmazonikaMuted"],
    ))

    def footer(canvas, report):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(17 * mm, 16 * mm, A4[0] - 17 * mm, 16 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(17 * mm, 12 * mm, "Amazonika Geoespacial - Prévia ambiental (não certificada)")
        canvas.drawRightString(A4[0] - 17 * mm, 12 * mm, f"Página {report.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    output = buffer.getvalue()
    if not output.startswith(b"%PDF") or len(output) > 12 * 1024 * 1024:
        raise ValueError("PDF inválido ou superior ao limite de 12 MB.")
    return output
