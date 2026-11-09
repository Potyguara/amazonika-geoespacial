"""Motor de composição de pranchas técnicas A2/A1 baseado em zonas mensuráveis.

Não modifica coordenadas, identificadores ou altitudes. Os modelos diferem
na composição gráfica, não na geodésia. Fontes são embutidas no PDF quando
os pacotes Debian/Ubuntu estão disponíveis no container.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from math import ceil
import math
from xml.sax.saxutils import escape

from pyproj import CRS, Transformer
from reportlab.lib import colors
from reportlab.lib.pagesizes import A1, A2, landscape, portrait
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph

from app.services.plant_memorial_v2 import _dms, _br_number, _azimuth_minutes
from app.services.plant_detail_elements import (
    confrontations_card, reference_card, signature_card, scale_card,
    compass_rose, grouped_label_positions, header_technical,
)

PAPER = {"A1": A1, "A2": A2}
SCALES = (200, 250, 500, 750, 1000, 1500, 2000, 2500,
          3000, 4000, 4500, 5000, 6000, 7500, 10000, 15000,
          20000, 25000, 50000, 100000, 200000, 500000)
PALETTES = {
    "classic_lateral": ("#154D3B", "#D6EBDD", "#C79A34", "#F7FAF7"),
    "cartographic_frame": ("#142F53", "#C7D9EE", "#C47D42", "#FFFEFA"),
    "modern_lateral": ("#202D37", "#B8E8DC", "#00A993", "#FAFCFC"),
}


def _fonts():
    options = (
        ("AKSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ("AKSans-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("AKDisplay", "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf"),
    )
    for name, filename in options:
        if name not in pdfmetrics.getRegisteredFontNames() and Path(filename).is_file():
            pdfmetrics.registerFont(TTFont(name, filename))
    regular = "AKSans" if "AKSans" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    bold = "AKSans-Bold" if "AKSans-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"
    display = "AKDisplay" if "AKDisplay" in pdfmetrics.getRegisteredFontNames() else bold
    return regular, bold, display


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def top(self):
        return self.y + self.h


def _color(value):
    return colors.HexColor(value)


def _pt_meter(scale):
    return 72.0 / (.0254 * scale)


def _text(pdf, value, x, y, size, font, color, max_width=None):
    value = str(value or "—")
    pdf.setFillColor(_color(color))
    pdf.setFont(font, size)
    if max_width and pdfmetrics.stringWidth(value, font, size) > max_width:
        # Exibir valor inteiro no memorial; na planta, usar quebra de linha
        # quando necessário em vez de truncamento de identificadores SIGEF.
        style = ParagraphStyle("wrapped", fontName=font, fontSize=size,
                               leading=size * 1.35, textColor=_color(color))
        p = Paragraph(escape(value), style)
        _, height = p.wrap(max_width, 500)
        p.drawOn(pdf, x, y - height + size)
        return height
    pdf.drawString(x, y, value)
    return size


def _card(pdf, rect, heading, palette):
    dark, pale, accent, paper = palette
    # Moldura de desenho técnico: cantos discretos, régua de acento
    # e uma única tipografia de seção, sem estética de dashboard.
    pdf.setFillColor(_color(paper))
    pdf.setStrokeColor(_color("#B7C5C0"))
    pdf.setLineWidth(.65)
    pdf.roundRect(rect.x, rect.y, rect.w, rect.h, 1.8, stroke=1, fill=1)
    pdf.setFillColor(_color(dark))
    pdf.rect(rect.x, rect.top - 24, rect.w, 24, fill=1, stroke=0)
    pdf.setFillColor(_color(accent))
    pdf.rect(rect.x, rect.top - 24, 3, 24, fill=1, stroke=0)
    regular, bold, _ = _fonts()
    _text(pdf, heading.upper(), rect.x + 11, rect.top - 16, 7.5, bold, "#FFFFFF")


def _details(pdf, rect, fields, palette, *, heading="IDENTIFICAÇÃO DO IMÓVEL"):
    _card(pdf, rect, heading, palette)
    regular, bold, _ = _fonts()
    usable = rect.h - 33
    step = usable / max(1, len(fields))
    if step < 22:
        raise ValueError("Bloco de identificação pequeno para os campos previstos.")
    for i, (key, value) in enumerate(fields):
        y = rect.top - 23 - i * step - 9
        _text(pdf, key.upper(), rect.x + 10, y, 6.1, bold, palette[2])
        _text(pdf, value or "Não informado", rect.x + 10, y - 11,
              7.5, regular, palette[0], rect.w - 20)


def _image_card(pdf, rect, image, source, palette):
    _card(pdf, rect, "PLANTA DE SITUAÇÃO", palette)
    box = Rect(rect.x + 7, rect.y + 21, rect.w - 14, rect.h - 52)
    if image is not None:
        # Preservar proporção original, evitando deformação da captura.
        pdf.drawImage(image, box.x, box.y, box.w, box.h,
                      preserveAspectRatio=True, anchor="c")
    else:
        _text(pdf, "Sem imagem de situação vinculada", box.x + 8,
              box.y + box.h/2, 7.0, _fonts()[0], palette[0])
    pdf.setStrokeColor(_color("#B7C5C0"))
    pdf.setLineWidth(.5)
    pdf.rect(box.x,box.y,box.w,box.h,fill=0,stroke=1)
    _text(pdf, (source or "Base cartográfica")[:64], rect.x + 9, rect.y + 8,
          5.8, _fonts()[0], palette[0])


def _signature_card_legacy(pdf, rect, owner, professional, palette):
    """Duas áreas de assinatura proporcionais, sem vácuo entre os campos."""
    _card(pdf, rect, "RESPONSABILIDADE E ASSINATURAS", palette)
    regular, bold, _ = _fonts()
    x, usable_w = rect.x + 12, rect.w - 24
    top_line = rect.top - 53
    second_line = max(rect.y + 52, top_line - 79)
    pdf.setStrokeColor(_color("#82938F"))
    pdf.setLineWidth(.7)
    pdf.line(x, top_line, x + usable_w, top_line)
    _text(pdf, "DETENTOR / PROPRIETÁRIO", x, top_line + 11, 6.7, bold, palette[0])
    _text(pdf, owner or "Não informado", x + 2, top_line - 15,
          7.3, regular, palette[0], usable_w - 4)
    pdf.line(x, second_line, x + usable_w, second_line)
    _text(pdf, "RESPONSÁVEL TÉCNICO", x, second_line + 11, 6.7, bold, palette[0])
    _text(pdf, professional.get("full_name") or "Não informado",
          x + 2, second_line - 15, 7.3, regular, palette[0], usable_w - 4)
    details = [
        str(professional.get(key) or "").strip()
        for key in ("profession", "crea", "visto")
    ]
    details = [value for value in details if value]
    if details and second_line - 30 > rect.y + 13:
        _text(pdf, " | ".join(details), x + 2, second_line - 28,
              6.3, regular, palette[0], usable_w - 4)
    if professional.get("art"):
        _text(pdf, "ART: " + str(professional["art"]), x + 2, rect.y + 9,
              6.3, bold, palette[0], usable_w - 4)


def _legend_card(pdf, rect, palette):
    _card(pdf, rect, "LEGENDA CARTOGRÁFICA", palette)
    regular = _fonts()[0]
    x, y = rect.x + 12, rect.top - 43
    entries = [("━━", "Limite do imóvel"), ("○", "Vértice"), ("■", "Marco"),
               ("+", "Grade UTM"), ("▧", "Área delimitada")]
    for sign, label in entries:
        _text(pdf, sign, x, y, 9, regular, palette[0])
        _text(pdf, label, x + 21, y, 7.0, regular, palette[0])
        y -= 18
        if y < rect.y + 10:
            break


def _neighbors_card_legacy(pdf, rect, parcels, palette):
    _card(pdf, rect, "CONFRONTAÇÕES", palette)
    regular = _fonts()[0]
    labels = []
    for p in parcels:
        for n in p.confrontants:
            if n and n not in labels:
                labels.append(n)
    for i, label in enumerate(labels[:7]):
        yy = rect.top - 40 - 17 * i
        if yy < rect.y + 11:
            break
        _text(pdf, "• " + str(label), rect.x + 11, yy, 6.6,
              regular, palette[0], rect.w - 22)
    if len(labels) > 7:
        _text(pdf, f"Mais {len(labels)-7} confrontações no memorial", rect.x + 11,
              rect.y + 8, 6.0, regular, palette[0], rect.w - 22)


def _summary_card(pdf, rect, parcels, palette):
    _card(pdf, rect, "RESUMO TÉCNICO", palette)
    regular, bold, _ = _fonts()
    pairs = [
        ("ÁREA", f"{_br_number(sum(p.area_ha for p in parcels),4)} ha"),
        ("PERÍMETRO", f"{_br_number(sum(p.perimeter for p in parcels),2)} m"),
        ("VÉRTICES", str(sum(len(p.points) for p in parcels))),
    ]
    gap = (rect.h - 28) / len(pairs)
    for i, (key, value) in enumerate(pairs):
        yy = rect.top - 41 - i * gap
        _text(pdf, key, rect.x + 11, yy, 6.2, bold, palette[2])
        _text(pdf, value, rect.x + 85, yy, 8.4, regular, palette[0])


def _rows(parcels, transformer):
    rows = []
    for p in parcels:
        for i, ((lon, lat), segment) in enumerate(zip(p.points, p.segments)):
            east, north = transformer.transform(lon, lat)
            rows.append((
                p.names[i], _dms(lon, "lon"), _dms(lat, "lat"),
                f"{east:.3f}", f"{north:.3f}",
                _br_number(p.altitudes[i], 2) if p.altitudes[i] is not None else "—",
                _azimuth_minutes(segment["azimuth"]), _br_number(segment["distance"], 2),
            ))
    return rows


def _table(pdf, box, rows, palette, *, columns=1, font_size=6.2):
    dark, pale, accent, paper = palette
    regular, bold, _ = _fonts()
    pdf.setStrokeColor(_color(dark))
    pdf.rect(box.x, box.y, box.w, box.h, fill=0, stroke=1)
    pdf.setFillColor(_color(dark))
    pdf.rect(box.x, box.top - 24, box.w, 24, fill=1, stroke=0)
    _text(pdf, "QUADRO DE COORDENADAS E SEGMENTOS", box.x + 9,
          box.top - 16, 8.0, bold, "#FFFFFF")
    header = ("VÉRTICE", "LONGITUDE", "LATITUDE", "ESTE (m)", "NORTE (m)",
              "ALT. (m)", "AZIMUTE", "DIST. (m)")
    fractions = (.145, .158, .155, .13, .13, .086, .089, .107)
    inner_top = box.top - 24
    row_h = max(12.0, font_size + 5.8)
    capacity = max(0, int((box.h - 24 - row_h - 6) // row_h))
    max_rows = capacity * columns
    shown = rows[:max_rows]
    # Distribuição equilibrada: blocos não ficam com 20 linhas vazias
    # quando a quantidade de vértices não é múltipla do número de colunas.
    balanced_rows = max(1, math.ceil(len(shown) / columns))
    cell_width = box.w / columns
    for col in range(columns):
        x = box.x + col * cell_width
        xcoords = [x + sum(fractions[:i]) * cell_width for i in range(8)]
        pdf.setFillColor(_color(pale))
        pdf.rect(x, inner_top - row_h, cell_width, row_h, fill=1, stroke=0)
        for i, label in enumerate(header):
            avail = fractions[i] * cell_width - 4
            fit_font = min(font_size, 6.2)
            while fit_font > 4.6 and pdfmetrics.stringWidth(label, bold, fit_font) > avail:
                fit_font -= .2
            if pdfmetrics.stringWidth(label, bold, fit_font) > avail:
                raise ValueError("Tabela não cabe na composição escolhida: aumente o papel.")
            _text(pdf, label, xcoords[i] + 2, inner_top - row_h + 3,
                  fit_font, bold, dark)
        for r in range(balanced_rows):
            idx = col * balanced_rows + r
            if idx >= len(shown):
                break
            row = shown[idx]
            yy = inner_top - row_h * (r + 2)
            is_mark = "-M-" in str(row[0]).upper() or str(row[0]).upper().startswith("M-")
            if is_mark:
                pdf.setFillColor(_color("#F4E9C8"))
                pdf.rect(x, yy, cell_width, row_h, fill=1, stroke=0)
            elif r % 2 == 0:
                pdf.setFillColor(_color("#F2F6F5"))
                pdf.rect(x, yy, cell_width, row_h, fill=1, stroke=0)
            for i, value in enumerate(row):
                avail = fractions[i] * cell_width - 4
                row_font = bold if is_mark else regular
                fit_font = font_size
                while fit_font > 4.6 and pdfmetrics.stringWidth(str(value), row_font, fit_font) > avail:
                    fit_font -= .2
                if pdfmetrics.stringWidth(str(value), row_font, fit_font) > avail:
                    raise ValueError(
                        f"Identificador ou coordenada não cabe na tabela: {value}. "
                        "Escolha papel maior ou outro modelo."
                    )
                _text(pdf, value, xcoords[i] + 2, yy + 3, fit_font, row_font, dark)
    return len(shown)


def _table_height(rows_count, columns, *, font_size=6.2):
    """Altura estritamente necessária, sem moldura inferior ociosa."""
    return 24 + max(12.0, font_size + 5.8) * (1 + math.ceil(rows_count / columns)) + 8


def _map(pdf, box, parcels, transformer, zone, hemi, scale_value, palette,
         elements, *, inset_left=0):
    from app.services.plant_memorial_v3 import _grid, _azimuth_and_distance
    from app.services.plant_label_layout import LabelLayout, Box
    points = [transformer.transform(*pos) for parcel in parcels for pos in parcel.points]
    xmin = min(p[0] for p in points); xmax = max(p[0] for p in points)
    ymin = min(p[1] for p in points); ymax = max(p[1] for p in points)
    actual = Rect(box.x + inset_left, box.y, box.w - inset_left, box.h)
    inner = Rect(actual.x + 25, actual.y + 28,
                 actual.w - 50, actual.h - 56)
    if inner.w <= 120 or inner.h <= 140:
        raise ValueError("Área cartográfica insuficiente para desenhar a planta.")
    def fits(n):
        factor = _pt_meter(n)
        return (xmax-xmin)*factor * 1.16 <= inner.w and (ymax-ymin)*factor * 1.16 <= inner.h
    if scale_value is None:
        scale = next((n for n in SCALES if fits(n)), None)
    else:
        scale = int(scale_value)
    if scale is None or not fits(scale):
        raise ValueError(
            "O perímetro não cabe na folha na escala selecionada. "
            "Escolha uma escala menor no desenho ou um papel maior."
        )
    factor = _pt_meter(scale)
    origin_x = inner.x + (inner.w - (xmax-xmin)*factor)/2
    origin_y = inner.y + (inner.h - (ymax-ymin)*factor)/2
    def xy(e, n):
        return origin_x + (e-xmin)*factor, origin_y + (n-ymin)*factor

    dark, pale, accent, paper = palette
    pdf.setFillColor(_color(paper))
    pdf.setStrokeColor(_color(dark))
    pdf.rect(box.x, box.y, box.w, box.h, stroke=1, fill=1)
    if elements.get("grid", True):
        _grid(pdf, (actual.x, actual.y, actual.w, actual.h), (xmin,ymin,xmax,ymax),
              xy, zone, hemi)
    # Isolar margens de graduação UTM e reservar móveis cartográficos
    # antes de posicionar os rótulos.
    label_layout = LabelLayout((actual.x+21, actual.y+24,
                                actual.w-42, actual.h-48))
    from shapely.geometry import Polygon as ShapelyPolygon, box as shape_box
    geometries=[
        ShapelyPolygon([xy(*transformer.transform(*pos)) for pos in p.points])
        for p in parcels
    ]
    def furniture_free(rect):
        shape=shape_box(rect.x,rect.y,rect.x+rect.w,rect.y+rect.h)
        return not any(geom.intersects(shape) for geom in geometries)
    # Escolher quadrante livre da geometria. Manter distância do bordo UTM.
    rose_candidates=[
        (actual.x+68,actual.y+103),
        (actual.x+68,actual.top-85),
        (actual.x+actual.w-72,actual.y+103),
    ]
    rose_x,rose_y=next(
        ((x,y) for x,y in rose_candidates
         if furniture_free(Box(x-52,y-52,104,104))),
        rose_candidates[0],
    )
    rose_rect=Box(rose_x-52,rose_y-52,104,104)
    scale_candidates=[
        Rect(actual.x+actual.w-220,actual.top-150,208,138),
        Rect(actual.x+actual.w-220,actual.y+20,208,138),
        Rect(actual.x+20,actual.top-150,208,138),
    ]
    scale_rect=next(
        (rect for rect in scale_candidates
         if furniture_free(rect)
         and not Box(rect.x,rect.y,rect.w,rect.h).intersects(rose_rect,3)),
        scale_candidates[0],
    )
    if elements.get("north",True):
        label_layout.reserved.append(rose_rect)
    if elements.get("scale_text",True) or elements.get("scale_bar",True):
        label_layout.reserved.append(Box(scale_rect.x-4,scale_rect.y-4,
                                         scale_rect.w+8,scale_rect.h+8))
    center = tuple(sum(p[i] for p in points)/len(points) for i in (0,1))
    center_xy = xy(*center)
    for p in parcels:
        coords = [xy(*transformer.transform(*pos)) for pos in p.points]
        path = pdf.beginPath()
        path.moveTo(*coords[0])
        for point in coords[1:]:
            path.lineTo(*point)
        path.close()
        pdf.setFillColor(_color(pale))
        pdf.setStrokeColor(_color(dark))
        pdf.setLineWidth(1.5)
        pdf.drawPath(path, stroke=1, fill=1)
        for cx, cy in coords:
            pdf.setFillColor(colors.white)
            pdf.circle(cx, cy, 2.4, fill=1, stroke=1)
        if elements.get("vertex_labels", True):
            for i, point in enumerate(coords):
                label_layout.place(pdf, [p.names[i]], point,
                                   desired=6.5, minimum=5.0,
                                   offsets=[(8,7),(-8,7),(8,-7),(-8,-7)],
                                   allow_callout=False, white_background=False)
        if elements.get("azimuths") or elements.get("distances") or elements.get("confrontants"):
            confrontant_labels = grouped_label_positions(p)
            for i, point in enumerate(coords):
                _azimuth_and_distance(
                    pdf, point, coords[(i+1) % len(coords)],
                    p.segments[i], p.confrontants[i], center_xy,
                    (actual.x, actual.y, actual.w, actual.h),
                    layout=label_layout,
                    show_azimuth=bool(elements.get("azimuths")),
                    show_distance=bool(elements.get("distances")),
                    show_confrontants=bool(elements.get("confrontants")) and i in confrontant_labels,
                )
    regular, bold, _ = _fonts()
    if elements.get("north", True):
        pdf.setFillColor(colors.white)
        pdf.circle(rose_x,rose_y,53,fill=1,stroke=0)
        compass_rose(pdf,rose_x,rose_y,36,palette)
    # Escala numérica e gráfica reunidas no mesmo quadro técnico.
    if elements.get("scale_text", True) or elements.get("scale_bar", True):
        scale_card(pdf,scale_rect,scale,palette)
    return scale


def _heading(pdf, title, place, paper_format, scale, w, h, palette, model):
    dark, pale, accent, paper = palette
    regular, bold, display = _fonts()
    if model == "classic_lateral":
        pdf.setFillColor(_color(dark))
        pdf.rect(24, h-99, w-48, 76, fill=1, stroke=0)
        pdf.setFillColor(_color(accent))
        pdf.rect(24, h-99, 7, 76, fill=1, stroke=0)
        _text(pdf, "PLANTA GEORREFERENCIADA", 42, h-48, 8, bold, "#DDECE4")
        _text(pdf, title.upper(), 42, h-82, 22, bold, "#FFFFFF", w*.6)
    elif model == "cartographic_frame":
        pdf.setFillColor(_color(dark))
        pdf.rect(24, h-106, w-48, 85, fill=1, stroke=0)
        _text(pdf, "PLANTA GEORREFERENCIADA", w*.34, h-48, 9, bold, "#E9D8C9")
        _text(pdf, title.upper(), 45, h-83, 25, display, "#FFFFFF", w*.8)
    else:
        pdf.setFillColor(_color(accent))
        pdf.rect(24, h-103, w-48, 3, fill=1, stroke=0)
        _text(pdf, "PLANTA GEORREFERENCIADA", 34, h-48, 9, bold, dark)
        _text(pdf, title.upper(), 34, h-87, 23, bold, dark, w*.65)
    # Dados cartográficos detalhados são desenhados após o cálculo de escala.


def _footer(pdf, w, stamp, disclaimer, palette):
    regular, _, _ = _fonts()
    pdf.setStrokeColor(_color(palette[0]))
    pdf.line(25, 34, w-25, 34)
    if disclaimer:
        _text(pdf, disclaimer, 29, 47, 5.7, regular, "#8B3434", w-60)
    _text(pdf, stamp, 29, 19, 5.7, regular, palette[0], w-55)


def _continuation(pdf, rows, start, w, h, title, stamp, palette):
    remaining = rows[start:]
    if not remaining:
        return
    rect = Rect(35, 65, w-70, h-185)
    while remaining:
        pdf.showPage()
        pdf.setPageSize((w, h))
        _heading(pdf, title, "Continuação do quadro de coordenadas", "A2",
                 None, w, h, palette, "modern_lateral")
        written = _table(pdf, rect, remaining, palette,
                         columns=2 if w>1100 else 1, font_size=7.6)
        if written <= 0:
            raise ValueError("Não há espaço para coordenadas nesta folha.")
        remaining = remaining[written:]
        _footer(pdf, w, stamp, None, palette)


def render_professional_plant(
    pdf, *, parcels, title, owner_name, owner_rg, owner_cpf,
    property_address, professional, raster, raster_source,
    paper_format, orientation, scale_denominator, plant_elements,
    stamp, croqui, disclaimer, layout_template, property_metadata,
    survey_date=None, magnetic_declination_degrees=None,
):
    """Desenha a planta e suas folhas de coordenadas; não chama showPage final.

    A camada superior de exportação chama showPage() antes do memorial.
    """
    if paper_format not in PAPER or orientation not in ("retrato","paisagem"):
        raise ValueError("Modelos profissionais: A2/A1, retrato ou paisagem.")
    w,h=(portrait if orientation=="retrato" else landscape)(PAPER[paper_format])
    palette=PALETTES[layout_template]
    fields=[
        ("Imóvel", title),
        ("Detentor / posseiro", owner_name),
        ("CPF", owner_cpf or "Não informado"),
        ("Localização", property_address),
        ("Área", f"{_br_number(sum(p.area_ha for p in parcels),4)} ha"),
        ("Perímetro", f"{_br_number(sum(p.perimeter for p in parcels),2)} m"),
        ("Situação jurídica", (property_metadata or {}).get("legal_status")),
        ("Natureza da área", (property_metadata or {}).get("area_nature")),
    ]
    xs = [point for parcel in parcels for point in parcel.points]
    mid_lon = sum(x for x,y in xs)/len(xs); mid_lat=sum(y for x,y in xs)/len(xs)
    zone = max(1,min(60,int((mid_lon+180)//6)+1))
    hemi = "S" if mid_lat<0 else "N"
    crs=CRS.from_proj4(
        f"+proj=utm +zone={zone} {'+south' if hemi=='S' else ''} "
        "+ellps=GRS80 +units=m +no_defs")
    transformer=Transformer.from_crs("EPSG:4674",crs,always_xy=True)
    from pyproj import Proj
    convergence=Proj(crs).get_factors(mid_lon,mid_lat).meridian_convergence
    if elements.get("magnetic_declination",False):
        from datetime import datetime
        from app.services.plant_geomagnetism import resolve_magnetic_declination
        ref_date=datetime.strptime(survey_date,"%d/%m/%Y").date() if survey_date else datetime.now().date()
        magnetic_declination_degrees,magnetic_source=resolve_magnetic_declination(
            parcels,ref_date,enabled=True,manual_degrees=magnetic_declination_degrees,
        )
    else:
        magnetic_source=None
    rows=_rows(parcels,transformer)
    elements=plant_elements or {}
    if elements.get("situation", True) and raster is None:
        raise ValueError("A Planta de Situação exige imagem capturada do mapa.")
    _heading(pdf,title,property_address,paper_format,scale_denominator,w,h,palette,layout_template)

    if orientation=="paisagem":
        # A2/A1 horizontal: prioridade ao mapa e aos cinco quadros.
        # A tabela de vértices segue em folha complementar sem perda de dados.
        top=h-118
        bottom=65
        side_w=max(325,min(505,w*.30))
        gap=14
        map_w=w-66-side_w-gap
        sidebar_x=33+map_w+gap
        main_rect=Rect(33,bottom,map_w,top-bottom)
        map_scale=_map(pdf,main_rect,parcels,transformer,zone,hemi,
                       scale_denominator,palette,elements)
        card_w=side_w
        available=top-bottom
        gap_y=7
        factor=(available-4*gap_y)/995
        parts=[230,135,250,140,240]
        heights=[v*factor for v in parts]
        t=top
        regions=[]
        for height in heights:
            regions.append(Rect(sidebar_x,t-height,card_w,height))
            t-=height+gap_y
        _details(pdf,regions[0],fields,palette)
        _image_card(pdf,regions[1],raster if elements.get("situation",True) else None,
                    raster_source,palette)
        confrontations_card(pdf,regions[2],parcels,palette)
        reference_card(pdf,regions[3],zone,hemi,
                       convergence=convergence,declination=magnetic_declination_degrees,
                       magnetic_source=magnetic_source,
                       palette=palette)
        signature_card(pdf,regions[4],owner_name,owner_cpf,professional,palette,
                       date_text=survey_date,owner_rg=owner_rg)
        header_technical(pdf,w,h,zone,hemi,map_scale,survey_date,palette,
                         dark_text=(layout_template=="modern_lateral"))
        _footer(pdf,w,stamp,disclaimer if croqui else None,palette)
        _continuation(pdf,rows,0,w,h,title,stamp,palette)
        return w,h,map_scale

    if layout_template=="classic_lateral":
        bottom_h=min(475, _table_height(len(rows),2,font_size=7.0))
        map_floor=54+bottom_h+25
        map_box=Rect(33,map_floor,w*.687-36,h-120-map_floor)
        sidebar_x=map_box.x+map_box.w+14
        sidebar_w=w-sidebar_x-33
        map_scale=_map(pdf,map_box,parcels,transformer,zone,hemi,
                       scale_denominator,palette,elements)
        t=map_box.top
        _details(pdf,Rect(sidebar_x,t-225,sidebar_w,225),fields,palette)
        _image_card(pdf,Rect(sidebar_x,t-405,sidebar_w,170),
                    raster if elements.get("situation",True) else None,
                    raster_source,palette)
        confrontations_card(pdf,Rect(sidebar_x,t-650,sidebar_w,235),parcels,palette)
        reference_card(pdf,Rect(sidebar_x,t-803,sidebar_w,143),zone,hemi,
                       convergence=convergence,declination=magnetic_declination_degrees,
                       magnetic_source=magnetic_source,
                       palette=palette)
        signature_card(pdf,Rect(sidebar_x,t-1043,sidebar_w,230),
                       owner_name,owner_cpf,professional,palette,date_text=survey_date,owner_rg=owner_rg)
        summary_y=max(410,t-1125)
        if summary_y+75 < t-1040:
            _summary_card(pdf,Rect(sidebar_x,summary_y,sidebar_w,75),parcels,palette)
        # 61 vértices em A2: tabela ampla, sem reduzir para fonte microscópica.
        # Aumentar o quadro desloca o rodapé do mapa, não sua borda superior.
        first=_table(pdf,Rect(33,54,w-66,bottom_h),rows,palette,columns=2,font_size=7.0)

    elif layout_template=="cartographic_frame":
        bottom_h=min(475, _table_height(len(rows),2,font_size=7.0))
        map_floor=54+bottom_h+25
        frame=Rect(33,map_floor,w-66,h-118-map_floor)
        # Painéis sobrepostos à moldura, respeitando uma faixa segura
        # para que a geometria permaneça inteiramente visível.
        map_scale=_map(pdf,frame,parcels,transformer,zone,hemi,
                       scale_denominator,palette,elements,inset_left=315)
        left=Rect(frame.x+15,frame.y+15,285,frame.h-30)
        # Apenas as regiões são declaradas aqui; a renderização usa os
        # componentes técnicos atuais, evitando referências legadas.
        cards=[
            Rect(left.x,left.top-220,left.w,220),
            Rect(left.x,left.top-390,left.w,160),
            Rect(left.x,left.top-635,left.w,235),
            Rect(left.x,left.top-788,left.w,143),
            Rect(left.x,left.top-1028,left.w,230),
        ]
        _details(pdf,cards[0],fields,palette)
        _image_card(pdf,cards[1],
                    raster if elements.get("situation",True) else None,
                    raster_source,palette)
        confrontations_card(pdf,cards[2],parcels,palette)
        reference_card(pdf,cards[3],zone,hemi,
                       convergence=convergence,declination=magnetic_declination_degrees,
                       magnetic_source=magnetic_source,
                       palette=palette)
        signature_card(pdf,cards[4],owner_name,owner_cpf,professional,palette,
                       date_text=survey_date,owner_rg=owner_rg)
        # Quadro adaptativo conforme a quantidade efetiva de vértices.
        first=_table(pdf,Rect(33,54,w-66,bottom_h),rows,palette,columns=2,font_size=7.0)

    else:  # modern_lateral
        left=Rect(34,490,w*.57-34,h-608)
        xright=left.x+left.w+14
        right=Rect(xright,490,w-xright-33,h-608)
        map_scale=_map(pdf,left,parcels,transformer,zone,hemi,
                       scale_denominator,palette,elements)
        right_table_h=min(right.h,_table_height(len(rows),1,font_size=6.6))
        compact_table=Rect(right.x,right.top-right_table_h,right.w,right_table_h)
        first=_table(pdf,compact_table,rows,palette,columns=1,font_size=6.6)
        half=(left.w-12)/2
        _details(pdf,Rect(left.x,305,half,170),fields[:6],palette)
        _image_card(pdf,Rect(left.x+half+12,305,half,170),
                    raster if elements.get("situation",True) else None,
                    raster_source,palette)
        confrontations_card(pdf,Rect(left.x,58,half,235),parcels,palette)
        signature_card(pdf,Rect(left.x+half+12,58,half,235),
                       owner_name,owner_cpf,professional,palette,date_text=survey_date,owner_rg=owner_rg)
        _summary_card(pdf,Rect(right.x,290,right.w,135),parcels,palette)
        reference_card(pdf,Rect(right.x,135,right.w,140),zone,hemi,
                       convergence=convergence,declination=magnetic_declination_degrees,
                       magnetic_source=magnetic_source,
                       palette=palette)
        header_technical(pdf,w,h,zone,hemi,map_scale,survey_date,palette,dark_text=True)
        _footer(pdf,w,stamp,disclaimer if croqui else None,palette)
        _continuation(pdf,rows,first,w,h,title,stamp,palette)
        return w,h,map_scale

    header_technical(pdf,w,h,zone,hemi,map_scale,survey_date,palette)
    _footer(pdf,w,stamp,disclaimer if croqui else None,palette)
    _continuation(pdf,rows,first,w,h,title,stamp,palette)
    return w,h,map_scale
