"""Relatório territorial em formato de dossiê editorial A4.

A apresentação é dinâmica; o código QR, os dados geoespaciais, as fontes
consultadas e as métricas vêm exclusivamente do snapshot emitido.
Não modifica registro, assinatura, hash nem URL de verificação.
"""
from __future__ import annotations

import io
import math
from datetime import datetime
from html import escape
from pathlib import Path

from PIL import Image, ImageOps
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas as canvas_module
from reportlab.platypus import Paragraph

from app.services.territorial_report import (
    _company_logo_path,
    _execution_rows_for_report,
    _fmt_datetime,
    _fmt_number,
    _pdf_font,
    _qr_png,
    _register_pdf_fonts,
    _sanitize_report_warning,
)

W, H = A4
GREEN = "#184B38"
DARK = "#143F31"
GOLD = "#C49D3E"
PALE = "#EDF5F1"
RED = "#B72A2B"
ROSE = "#FAE7E6"
LINE = "#D3DED8"
INK = "#223D33"
MUTED = "#62776D"
WHITE = "#FFFFFF"


class Dossier:
    def __init__(self, pdf_path: Path, snapshot: dict):
        _register_pdf_fonts()
        self.sans = _pdf_font("AmazonikaSans", "Helvetica")
        self.bold = _pdf_font("AmazonikaSansBold", "Helvetica-Bold")
        self.serif = _pdf_font("AmazonikaSerifBold", "Times-Bold")
        self.c = canvas_module.Canvas(
            str(pdf_path), pagesize=A4, pageCompression=1,
        )
        self.c.setTitle("Relatório Técnico · Dossiê — " + snapshot["tracking_code"])
        self.c.setAuthor("AMAZONIKA ENGENHARIA LTDA")
        self.snapshot = snapshot
        self.page = 0
        self.pages = []

    def rect(self, x, top, w, h, fill=WHITE, stroke=None, radius=0, thick=0.7):
        c = self.c
        c.setLineWidth(thick)
        c.setFillColor(colors.HexColor(fill))
        c.setStrokeColor(colors.HexColor(stroke or fill))
        if radius:
            c.roundRect(x, H-top-h, w, h, radius, fill=1, stroke=int(bool(stroke)))
        else:
            c.rect(x, H-top-h, w, h, fill=1, stroke=int(bool(stroke)))

    def text(self, x, top, value, size=8, color=INK, font=None, align="left"):
        c = self.c
        c.setFont(font or self.sans, size)
        c.setFillColor(colors.HexColor(color))
        y = H - top - size
        value = str(value if value is not None else "—")
        if align == "right":
            c.drawRightString(x, y, value)
        elif align == "center":
            c.drawCentredString(x, y, value)
        else:
            c.drawString(x, y, value)

    def paragraph(self, x, top, value, width, size=8, leading=12,
                  color=INK, bold=False, align=0):
        style = ParagraphStyle(
            "body", fontName=self.bold if bold else self.sans,
            fontSize=size, leading=leading, textColor=colors.HexColor(color),
            alignment=align, splitLongWords=1,
        )
        p = Paragraph(escape(str(value)).replace("\n", "<br/>"), style)
        _, height = p.wrap(width, 800)
        p.drawOn(self.c, x, H-top-height)
        return height

    def line(self, x, top, x2, color=LINE, thickness=0.7):
        self.c.setStrokeColor(colors.HexColor(color))
        self.c.setLineWidth(thickness)
        self.c.line(x, H-top, x2, H-top)

    def image(self, path_or_image, x, top, w, h, preserve=False):
        try:
            self.c.drawImage(
                ImageReader(path_or_image), x, H-top-h, w, h,
                preserveAspectRatio=preserve, anchor="c", mask="auto",
            )
        except Exception:
            pass

    def footer(self):
        self.line(50, 812, 545, LINE)
        self.text(51, 817,
                  "Amazonika Geoespacial · " + self.snapshot["tracking_code"],
                  6.2, MUTED)
        self.text(298, 817, "CNPJ 49.158.834/0001-19", 6.2, MUTED)
        self.text(544, 817, f"Página {self.page}", 6.2, GREEN,
                  self.bold, "right")

    def finish_page(self):
        self.footer()
        self.c.showPage()

    def header(self):
        self.page += 1
        self.rect(0, 0, W, 8, GREEN)
        self.rect(0, 0, 126, 8, GOLD)
        logo = _company_logo_path()
        if logo.exists():
            self.image(str(logo), 50, 23, 28, 30, preserve=True)
        self.text(84, 28, "A M A Z O N I K A   E N G E N H A R I A",
                  8.2, GREEN, self.bold)
        self.text(545, 30, "R E L A T Ó R I O  D E  A N Á L I S E  T E R R I T O R I A L",
                  5.5, MUTED, self.sans, "right")
        self.rect(50, 61, 62, 2, GOLD)
        self.line(112, 62, 545)

    def section(self, top, number, title):
        self.rect(50, top, 23, 24, GREEN, radius=4)
        self.text(61.5, top+5, number, 11, WHITE, self.bold, "center")
        self.text(84, top+5, title.upper(), 10, GREEN, self.bold)
        self.line(84, top+28, 545)

    def metric(self, x, top, w, label, value, color=GREEN, h=72):
        self.rect(x, top, w, h, WHITE, LINE, radius=6)
        self.rect(x, top, w, 5, color)
        self.text(x+12, top+15, label.upper(), 6.4, GOLD, self.bold)
        self.text(x+12, top+33, value, 17, color, self.serif)

    def source_row(self, row, top, n=0):
        x = 50
        w = [119, 71, 65, 40, 65, 44, 53, 38]
        values = [
            row.get("source_name") or "—",
            row.get("institution") or "—",
            ("INTERFERE" if row.get("intersects") else "SEM INTERF.")
              if row.get("status") == "ANALYZED"
              else str(row.get("status") or "FALHA"),
            str(row.get("matched_features") or 0)
              if row.get("status") == "ANALYZED" else "—",
            _fmt_number(row.get("overlap_hectares") or 0)
              if row.get("status") == "ANALYZED" else "—",
            _fmt_number(row.get("overlap_percent") or 0, 2)
              if row.get("status") == "ANALYZED" else "—",
            (f"{_fmt_number(row.get('nearest_distance_meters'), 2)} m"
             if row.get("nearest_distance_meters") is not None else "—"),
            str(row.get("reference_date") or "—"),
        ]
        if n % 2:
            self.rect(50, top, 495, 35, "#F7FAF8")
        self.line(50, top+35, 545)
        for width, value in zip(w, values):
            self.paragraph(x+5, top+10, value, width-9,
                           6.5 if width > 55 else 6.2, 8.3,
                           RED if value == "INTERFERE" else INK,
                           value == "INTERFERE")
            x += width

    def source_header(self, top):
        self.rect(50, top, 495, 27, GREEN)
        widths = [119, 71, 65, 40, 65, 44, 53, 38]
        labels = ["FONTE", "ÓRGÃO", "SITUAÇÃO", "FEIÇÕES",
                  "ÁREA (HA)", "%", "DISTÂNCIA", "REF."]
        x = 50
        for width, label in zip(widths, labels):
            self.text(x+5, top+9, label, 5.4, WHITE, self.bold)
            x += width

    def qr_green(self, url):
        """Matriz QR real do rastreio, nas cores institucionais."""
        with Image.open(io.BytesIO(_qr_png(url))) as im:
            return ImageOps.colorize(im.convert("L"), black=GREEN, white=WHITE)

    def logo_cover(self):
        self.page += 1
        self.rect(0, 0, W, 219, GREEN)
        self.rect(0, 0, 125, 8, GOLD)
        self.rect(0, 216, W, 3, GOLD)
        # Linhas finas remetem às curvas de nível da capa de referência.
        c = self.c
        c.saveState()
        c.setStrokeColor(colors.HexColor("#31604E"))
        c.setLineWidth(.45)
        for j in range(8):
            offset = j*12
            p = c.beginPath()
            p.moveTo(225, H-15-offset)
            p.curveTo(270, H-4-offset, 310, H-42-offset,
                      353, H-18-offset)
            p.curveTo(406, H-3-offset, 475, H-45-offset,
                      595, H-18-offset)
            c.drawPath(p, stroke=1)
        c.restoreState()
        self.rect(50, 33, 48, 48, WHITE, radius=7)
        logo = _company_logo_path()
        if logo.exists():
            self.image(str(logo), 53, 35, 43, 44, True)
        self.text(110, 40, "AMAZONIKA ENGENHARIA LTDA", 9.1, WHITE, self.bold)
        self.text(110, 58, "T O P O G R A F I A  E  M E I O  A M B I E N T E",
                  6.1, "#DCE8E2")
        self.text(545, 43, "CNPJ 49.158.834/0001-19",
                  6.2, "#C9DAD1", align="right")
        self.text(545, 57, "www.amazonikaengenharia.com.br",
                  6.2, "#C9DAD1", align="right")
        self.text(50, 113, "R E L A T Ó R I O   T É C N I C O   ·   D O S S I Ê",
                  7, GOLD, self.bold)
        self.text(50, 138, "Análise Territorial", 28, WHITE, self.serif)
        self.paragraph(50, 182, self.snapshot.get("analysis_name") or "—",
                       300, 11, 13, "#D7E8DD")
        area = self.snapshot.get("area_hectares")
        self.text(545, 122, "ÁREA ANALISADA", 7, GOLD, self.bold, "right")
        self.text(545, 142,
                  _fmt_number(area) + " ha" if area is not None else "PONTO",
                  16, GOLD, self.serif, "right")
        self.text(545, 184,
                  f"{self.snapshot.get('geometry_kind') or '—'}  ·  SIRGAS 2000 / EPSG:4674",
                  7, WHITE, align="right")

    def first_page(self, map_path, url, rows, stats):
        self.logo_cover()
        # Coluna lateral: identificação.
        self.rect(50, 237, 164, 254, WHITE, LINE, radius=6)
        self.rect(50, 237, 164, 23, GREEN)
        self.rect(50, 237, 4, 23, GOLD)
        self.text(62, 244, "I D E N T I F I C A Ç Ã O", 7, WHITE, self.bold)
        sp = self.snapshot
        dt = datetime.fromisoformat(sp["issued_at"])
        fields = [
            ("SISTEMA EMISSOR", sp.get("system") or "Amazonika Geoespacial"),
            ("RESPONSÁVEL PELA ANÁLISE", (sp.get("executor") or {}).get("name") or "—"),
            ("USUÁRIO EMISSOR", (sp.get("issuer") or {}).get("name") or "—"),
            ("DATA/HORA DA ANÁLISE",
             _fmt_datetime(datetime.fromisoformat(sp["analysis_created_at"]))
             if sp.get("analysis_created_at") else "—"),
            ("DATA/HORA DA EMISSÃO", _fmt_datetime(dt)),
            ("GEOMETRIA", sp.get("geometry_kind") or "—"),
            ("SRC", "SIRGAS 2000 · EPSG:4674"),
            ("PERÍMETRO", _fmt_number(sp.get("perimeter_meters"), 2) + " m"
             if sp.get("perimeter_meters") is not None else "—"),
        ]
        y = 270
        for label, value in fields:
            self.text(60, y, label, 5.6, GOLD, self.bold)
            h = self.paragraph(60, y+9, value, 144, 6.3, 8.2, INK, True)
            y += max(25, 11+h+3)
            if y > 491:
                break

        # Indicadores da referência, com cores de estado.
        self.metric(232, 237, 150, "ÁREA ANALISADA",
                    _fmt_number(sp.get("area_hectares"))+" ha"
                    if sp.get("area_hectares") is not None else "Ponto",
                    GOLD, 72)
        self.metric(390, 237, 155, "BASES ANALISADAS",
                    f"{stats['analyzed']}/{stats['expected']}", "#30745A", 72)
        self.metric(232, 318, 150, "INTERFERÊNCIAS",
                    str(stats["overlap"]), RED, 72)
        self.metric(390, 318, 155, "ALERTAS",
                    str(stats["alerts"]), "#30745A", 72)

        red_case = stats["overlap"] > 0
        self.rect(232, 400, 313, 62,
                  ROSE if red_case else PALE, "#E1BAB7" if red_case else LINE,
                  radius=6)
        self.rect(232, 400, 5, 62, RED if red_case else "#2F8564")
        self.text(252, 412, "VEREDITO DA ANÁLISE",
                  6.5, RED if red_case else GREEN, self.bold)
        self.text(252, 428,
                  f"{stats['overlap']} interferência(s) identificada(s)"
                  if red_case else "Nenhuma interferência identificada",
                  13, RED if red_case else GREEN, self.serif)
        self.text(252, 450,
                  f"{stats['overlap']} de {stats['analyzed']} base(s) interfere(m) · {stats['alerts']} alerta(s)",
                  6.7, MUTED)

        # Mapa: a imagem original é recortada para retirar título e legendas
        # redundantes do painel, tal como no dossiê de referência.
        self.rect(232, 470, 313, 147, WHITE, LINE)
        try:
            with Image.open(map_path) as im:
                cropped = im.crop((55, 135, 1545, 790)).convert("RGB")
                self.image(cropped, 236, 474, 305, 139)
        except Exception:
            self.text(245, 510, "Mapa indisponível", 9, MUTED)
        self.rect(232, 624, 4, 21, GOLD)
        self.paragraph(243, 626,
            "Figura 1 — Contexto territorial da área analisada e interferências identificadas.",
            302, 6.3, 8, MUTED)

        # QR lateral e aviso de resultado.
        self.rect(50, 500, 164, 280, WHITE, LINE, radius=6)
        self.rect(50, 500, 164, 22, GREEN)
        self.rect(50, 500, 4, 22, GOLD)
        self.text(62, 507, "V E R I F I C A Ç Ã O", 7, WHITE, self.bold)
        self.rect(77, 532, 110, 110, WHITE, LINE, radius=5)
        self.image(self.qr_green(url), 83, 538, 98, 98)
        self.text(132, 652, "CÓDIGO", 6.1, GOLD, self.bold, "center")
        self.text(132, 666, sp["tracking_code"], 10, GREEN, self.bold, "center")
        self.paragraph(64, 693,
            "Aponte a câmera do celular para consultar a emissão registrada e acessar o documento vinculado.",
            135, 6.6, 10, MUTED, align=1)
        self.rect(232, 659, 313, 121, ROSE if red_case else PALE,
                  "#E2B8B5" if red_case else LINE, radius=6)
        self.rect(232, 659, 5, 121, RED if red_case else GREEN)
        self.text(251, 674,
                  "INTERFERÊNCIAS IDENTIFICADAS" if red_case
                  else "RESULTADO DA ANÁLISE",
                  8.4, RED if red_case else GREEN, self.bold)
        if red_case:
            msg = (
                f"Foram identificadas interferências espaciais em {stats['overlap']} "
                "fonte(s) territorial(is). As ocorrências devem ser avaliadas "
                "em conjunto com os atos, cadastros e documentos emitidos "
                "pelos órgãos responsáveis. Os percentuais por fonte não "
                "devem ser somados quando houver coincidência entre bases."
            )
        else:
            msg = "Nenhuma interferência nas bases efetivamente analisadas. " \
                  "A ausência de interferência não constitui certidão negativa."
        self.paragraph(252, 698, msg, 278, 7.2, 11.2, INK)
        self.finish_page()

    def second_page(self, url, rows, stats):
        self.header()
        self.section(79, "1", "Bases territoriais consultadas")
        widths = [94, 94, 94, 107, 106]
        labels = ["PREVISTAS", "ANALISADAS", "INTERFEREM",
                  "SEM INTERFERÊNCIA", "INDISPONÍVEIS / FALHA"]
        vals = [stats["expected"], stats["analyzed"], stats["overlap"],
                stats["clear"], stats["alerts"]]
        x = 50
        for i, (w, label, val) in enumerate(zip(widths, labels, vals)):
            color = RED if i == 2 and val else (GOLD if i < 2 else "#30745A")
            self.metric(x, 115, w-7, label, str(val), color, 61)
            x += w

        self.source_header(188)
        for i, row in enumerate(rows[:5]):
            self.source_row(row, 215+i*35, i)

        y = 215 + min(len(rows), 5)*35 + 23
        self.section(y, "2", "Ficha das interferências")
        y += 41
        overlaps = [r for r in rows if r.get("status") == "ANALYZED"
                    and r.get("intersects")]
        if overlaps:
            for row in overlaps[:2]:
                self.rect(50, y, 495, 86, WHITE, LINE, radius=6)
                self.rect(50, y, 5, 86, RED)
                self.paragraph(68, y+9, row.get("source_name") or "—",
                               390, 13, 15, GREEN, True)
                self.text(524, y+12, "INTERFERE", 7, RED, self.bold, "right")
                self.text(68, y+30,
                          f"{row.get('institution') or '—'} · Referência {row.get('reference_date') or '—'}",
                          7, MUTED)
                labels = ["FEIÇÕES", "ÁREA (HA)", "% DA ÁREA", "DISTÂNCIA"]
                vals = [
                    str(row.get("matched_features") or 0),
                    _fmt_number(row.get("overlap_hectares") or 0),
                    _fmt_number(row.get("overlap_percent") or 0, 2),
                    f"{_fmt_number(row.get('nearest_distance_meters'), 2)} m"
                    if row.get("nearest_distance_meters") is not None else "—",
                ]
                for j in range(4):
                    px = 68+j*118
                    self.text(px, y+49, labels[j], 5.9, GOLD, self.bold)
                    self.text(px, y+62, vals[j], 8.5, INK, self.bold)
                y += 95

            # Síntese tabular vermelha, presente no modelo de referência.
            if len(overlaps) <= 2 and y + 56 < 650:
                self.rect(50, y, 495, 23, RED)
                columns = [
                    (62, "FONTE"), (260, "ÓRGÃO"), (378, "FEIÇÕES"),
                    (437, "ÁREA (HA)"), (507, "%"),
                ]
                for px, label in columns:
                    self.text(px, y+8, label, 6, WHITE, self.bold)
                y += 23
                for overlap in overlaps:
                    self.rect(50, y, 495, 31, WHITE, LINE)
                    self.paragraph(62, y+9, overlap.get("source_name") or "—",
                                   190, 6.5, 8, INK)
                    self.text(260, y+9, overlap.get("institution") or "—", 6.3, INK)
                    self.text(378, y+9, str(overlap.get("matched_features") or 0), 6.3, INK)
                    self.text(437, y+9, _fmt_number(overlap.get("overlap_hectares") or 0), 6.3, INK)
                    self.text(507, y+9, _fmt_number(overlap.get("overlap_percent") or 0, 2), 6.3, RED)
                    y += 31
                y += 9
        else:
            self.rect(50, y, 495, 51, PALE, LINE, radius=5)
            self.text(67, y+15, "Nenhuma interferência registrada.", 11, GREEN, self.bold)
            y += 60

        # Os demais itens recebem páginas de continuação, se necessário.
        if y > 525 or len(rows) > 5 or len(overlaps) > 2:
            self.finish_page()
            self.continuation(rows[5:], overlaps[2:], url)
            return

        warnings = list(self.snapshot.get("warnings") or [])
        if warnings:
            self.finish_page()
            self.continuation([], [], url)
            return
        self.final_panel(y+10, url)

    def continuation(self, rows, overlaps, url):
        self.header()
        self.section(80, "3", "Detalhamento das bases consultadas")
        self.source_header(120)
        y = 147
        for i, row in enumerate(rows):
            if y+35 > 720:
                self.finish_page()
                self.header()
                self.source_header(100)
                y = 127
            self.source_row(row, y, i)
            y += 35
        for row in overlaps:
            if y+90 > 710:
                self.finish_page()
                self.header()
                y = 90
            self.rect(50, y, 495, 72, WHITE, LINE, radius=6)
            self.rect(50, y, 5, 72, RED)
            self.paragraph(66, y+10, row.get("source_name") or "—",
                           390, 12, 15, GREEN, True)
            self.text(66, y+38,
                      "Área: "+_fmt_number(row.get("overlap_hectares") or 0)+" ha  ·  "+
                      _fmt_number(row.get("overlap_percent") or 0, 2)+"%  ·  "+
                      str(row.get("matched_features") or 0)+" feições",
                      8, INK)
            y += 80
        warnings = []
        for warning in self.snapshot.get("warnings") or []:
            text = _sanitize_report_warning(str(warning))
            if text and text not in warnings:
                warnings.append(text)
        if warnings:
            if y > 540:
                self.finish_page()
                self.header()
                y = 90
            self.rect(50, y+10, 495, 26, "#FFF5D9", "#D8BC6B", radius=4)
            self.text(63, y+18, "ADVERTÊNCIAS DA EXECUÇÃO", 8, "#8F7529", self.bold)
            y += 45
            for warning in warnings:
                h = self.paragraph(65, y, warning, 470, 7.0, 10, INK)
                y += h + 12
                if y > 540:
                    self.finish_page()
                    self.header()
                    y = 90
        if y > 540:
            self.finish_page()
            self.header()
            y = 90
        self.final_panel(y+10, url)

    def final_panel(self, y, url):
        self.rect(50, y, 495, 85, "#FFF5D9", "#D8BC6B", radius=6)
        self.rect(50, y, 5, 85, "#8F7529")
        self.text(67, y+14, "LIMITAÇÕES E RESPONSABILIDADE TÉCNICA",
                  8, "#8F7529", self.bold)
        self.paragraph(67, y+32,
            "Os resultados refletem exclusivamente as bases, versões e geometrias "
            "efetivamente disponíveis e processadas na data da análise. "
            "A ausência de interferência não constitui certidão negativa "
            "e não substitui documentos, anuências, certidões ou "
            "manifestações formais dos órgãos competentes.",
            460, 7.5, 11, INK)
        y += 100
        self.rect(50, y, 495, 142, WHITE, LINE, radius=7)
        self.rect(50, y, 495, 23, GREEN)
        self.rect(50, y, 4, 23, GOLD)
        self.text(63, y+7, "VERIFICAÇÃO E RASTREABILIDADE",
                  8, WHITE, self.bold)
        self.rect(65, y+32, 101, 100, WHITE, LINE, radius=5)
        self.image(self.qr_green(url), 69, y+36, 92, 92)
        sp = self.snapshot
        self.text(183, y+36, "CÓDIGO", 6.2, GOLD, self.bold)
        self.text(183, y+49, sp["tracking_code"], 12, GREEN, self.bold)
        issuer = (sp.get("issuer") or {}).get("name") or "—"
        self.text(183, y+76, "Sistema   Amazonika Geoespacial", 6.2, INK)
        self.paragraph(183, y+89, "Emissor   "+issuer, 173, 6, 8, INK)
        self.text(183, y+113,
                  "Emissão   "+_fmt_datetime(datetime.fromisoformat(sp["issued_at"])),
                  6, INK)
        self.rect(364, y+32, 1, 102, LINE)
        self.text(376, y+36, "AMAZONIKA ENGENHARIA LTDA",
                  6.6, GREEN, self.bold)
        company = [
            "Av. Almirante Barroso 620-B",
            "CEP 68900-401 · Central · Macapá/AP",
            "CNPJ: 49.158.834/0001-19",
            "96 98803-6439 / 96 9141-0943",
            "www.amazonikaengenharia.com.br",
            "amazonika@amazonikaengenharia.com.br",
        ]
        for j, val in enumerate(company):
            self.text(376, y+51+j*12, val, 5.7, MUTED)
        self.finish_page()


def build_report_pdf_dossie(
    snapshot: dict,
    map_path: Path,
    pdf_path: Path,
    verification_url: str,
) -> None:
    rows = _execution_rows_for_report(snapshot)
    stats = {
        "expected": len(rows),
        "analyzed": sum(r.get("status") == "ANALYZED" for r in rows),
        "overlap": sum(r.get("status") == "ANALYZED" and r.get("intersects") is True
                       for r in rows),
        "clear": sum(r.get("status") == "ANALYZED" and r.get("intersects") is False
                     for r in rows),
        "alerts": sum(r.get("status") in ("UNAVAILABLE", "FAILED") for r in rows),
    }
    doc = Dossier(pdf_path, snapshot)
    doc.first_page(map_path, verification_url, rows, stats)
    doc.second_page(verification_url, rows, stats)
    doc.c.save()
