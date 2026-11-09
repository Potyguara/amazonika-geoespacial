"""Planta técnica de folha única e memorial paginado — SIRGAS2000 / GRS80.

A escala é física e não é ajustada silenciosamente. Todos os vértices da
planta devem caber na mesma folha; quando não couberem, o usuário escolhe
um formato maior ou reduz o conjunto de áreas.
"""
from __future__ import annotations

import io
import math
from datetime import datetime
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from pyproj import CRS, Transformer
from reportlab.lib import colors
from reportlab.lib.pagesizes import A0, A1, A2, A3, A4, landscape, portrait
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from app.services.plant_label_layout import LabelLayout, Box
from app.services.plant_memorial_v2 import (
    DISCLAIMER, Parcel, _dms, _azimuth_minutes, _br_number,
    _raster_reader, build_joint_memorial,
)

PAPERS = {"A4": A4, "A3": A3, "A2": A2, "A1": A1, "A0": A0}
SCALES = (100, 200, 250, 500, 750, 1000, 1500, 2000, 2500, 5000,
          7500, 10000, 15000, 20000, 25000, 50000, 100000, 200000, 500000)
GREEN = colors.HexColor("#23543D")
DARK = colors.HexColor("#23342A")
PALE = colors.HexColor("#F0F5F1")
GRID = colors.HexColor("#CCD8D0")
RULE = colors.HexColor("#839E8B")
INK = colors.HexColor("#191F1C")
FONT_MIN = 6.0


def _pt_per_meter(scale: int) -> float:
    return 72 / (.0254 * scale)


def _clip_rect(pdf, left, bottom, width, height):
    clipping = pdf.beginPath()
    clipping.rect(left, bottom, width, height)
    pdf.clipPath(clipping, stroke=0, fill=0)


def _columns(width):
    fractions = (.12, .16, .16, .135, .135, .085, .115, .09)
    starts = [0.0]
    for fraction in fractions[:-1]:
        starts.append(starts[-1] + fraction * width)
    widths = [v * width for v in fractions]
    return list(zip(starts, widths))


def _layout(projected, *, vertex_count, paper, orientation, scale, show_coordinates=True, layout_template='lateral'):
    fmt = (paper or "A4").upper()
    if fmt not in PAPERS:
        raise ValueError("Formato inválido. Escolha A4, A3, A2, A1 ou A0.")
    if orientation not in ("paisagem", "retrato"):
        raise ValueError("Orientação inválida. Escolha paisagem ou retrato.")
    w, h = (landscape if orientation == "paisagem" else portrait)(PAPERS[fmt])
    frame = (23, 23, w-46, h-46)
    if layout_template not in ('lateral', 'inferior'):
        raise ValueError('Modelo de planta inválido.')
    side_x = w * (.73 if orientation == "paisagem" else .68)
    map_left, map_right = 38, side_x - 15
    available_width = map_right - map_left
    row_h = 13 if fmt in ("A4", "A3") else 14
    title_h = 23
    first_rows = min(vertex_count, 8) if layout_template == 'inferior' else vertex_count
    table_h = title_h + (first_rows + 1) * row_h + 7 if show_coordinates else 0
    # Faixa exclusiva para escala gráfica e escala numérica; fora da grade UTM.
    map_bottom = 42 + table_h + 39
    # Faixa acima da grade reservada a rosa dos ventos e quadro magnético.
    map_top = h - 88
    map_w = available_width
    map_h = map_top - map_bottom
    if map_h < 145 or available_width < 210:
        raise ValueError(
            f"Não é possível incluir {vertex_count} vértices na mesma prancha {fmt} "
            "com leitura adequada. Escolha papel maior ou selecione menos polígonos."
        )
    allpoints = [p for ring in projected for p in ring]
    x0 = min(p[0] for p in allpoints)
    y0 = min(p[1] for p in allpoints)
    x1 = max(p[0] for p in allpoints)
    y1 = max(p[1] for p in allpoints)
    bounds = (x0, y0, x1, y1)
    def fits(candidate):
        f = _pt_per_meter(candidate)
        return max(1., x1-x0)*f*1.18 <= map_w and max(1., y1-y0)*f*1.18 <= map_h
    suggested = next((den for den in SCALES if fits(den)), None)
    if suggested is None:
        raise ValueError(f"O imóvel não cabe em {fmt}. Escolha uma folha maior.")
    chosen = suggested if scale is None else int(scale)
    if not 50 <= chosen <= 1000000:
        raise ValueError("Denominador da escala deve estar entre 50 e 1.000.000.")
    if not fits(chosen):
        raise ValueError(
            f"Escala 1:{chosen:,} não cabe no formato {fmt} ({orientation}). "
            f"Utilize 1:{suggested:,} ou uma escala menor no desenho."
        )
    table_width = w - 76 if layout_template == 'inferior' else map_w
    return (fmt, w, h, side_x, bounds,
            (map_left, map_bottom, map_w, map_h), (38, 42, table_width, table_h), chosen)


def _fit_text(pdf, text, max_width, font="Helvetica", max_size=8.0, min_size=5.8):
    size = max_size
    while size > min_size and stringWidth(text, font, size) > max_width:
        size -= .25
    pdf.setFont(font, max(min_size, size))
    if stringWidth(text, font, max(min_size, size)) > max_width:
        # Não deixar extravasar: quebra somente para rótulos de quadros.
        return False
    return True


def _cell(pdf, x, y_top, width, heading, value, max_height=40):
    paragraph = Paragraph(
        escape(str(value or "Não informado")),
        ParagraphStyle("cell", fontName="Helvetica", fontSize=7.6,
                       leading=9.5, textColor=DARK),
    )
    _, height = paragraph.wrap(max(35, width-15), 500)
    if height > max_height - 17:
        raise ValueError(f"O campo '{heading}' excede a área de identificação.")
    pdf.setFillColor(PALE)
    pdf.rect(x, y_top-max_height, width, max_height, fill=1, stroke=0)
    pdf.setStrokeColor(RULE)
    pdf.setLineWidth(.45)
    pdf.line(x,y_top-max_height,x+width,y_top-max_height)
    pdf.setFont("Helvetica-Bold", 6.5)
    pdf.setFillColor(GREEN)
    pdf.drawString(x+7, y_top-10, heading.upper())
    paragraph.drawOn(pdf,x+7,y_top-14-height)
    return y_top-max_height


def _azimuth_and_distance(pdf, p0, p1, row, confrontant, inner_point,
                          viewport, *, layout=None, show_azimuth=True,
                          show_distance=True, show_confrontants=True):
    x0,y0=p0
    x1,y1=p1
    dx,dy=x1-x0,y1-y0
    length=math.hypot(dx,dy)
    if length<1: return
    angle=math.degrees(math.atan2(dy,dx))
    nx,ny=-dy/length,dx/length
    mx,my=(x0+x1)/2,(y0+y1)/2
    cx,cy=inner_point
    if (cx-mx)*nx+(cy-my)*ny>0: nx,ny=-nx,-ny
    manager=layout if layout is not None else LabelLayout(viewport)
    lines=[]
    if show_azimuth: lines.append("Az. "+_azimuth_minutes(row["azimuth"]))
    if show_distance: lines.append("Dist. "+_br_number(row["distance"],2)+" m")
    if lines:
        manager.place(pdf,lines,(mx,my),angle=angle,
                      offsets=[(nx*13,ny*13),(-nx*13,-ny*13),
                               (nx*23,ny*23),(-nx*23,-ny*23),
                               (nx*34,ny*34),(-nx*34,-ny*34)],
                      desired=7.1,minimum=6.0)
    if show_confrontants and confrontant.strip():
        manager.place(pdf,[confrontant.strip()],(mx,my),
                      angle=angle,color=GREEN,
                      offsets=[(nx*31,ny*31),(nx*45,ny*45),
                               (-nx*31,-ny*31),(-nx*45,-ny*45)],
                      desired=7.2,minimum=6.0)


def _grid(pdf, viewport, bounds, xy, zone, hemi):
    left,bottom,width,height=viewport
    x0,y0,x1,y1=bounds
    span=max(x1-x0,y1-y0,1)
    step=10**math.floor(math.log10(max(span/5,1)))
    if span/step>8: step*=2
    if span/step<3: step/=2
    while step*abs(xy(x0+1,y0)[0]-xy(x0,y0)[0]) < 55: step*=2
    pdf.saveState()
    _clip_rect(pdf,left,bottom,width,height)
    pdf.setStrokeColor(GRID);pdf.setLineWidth(.5)
    pdf.setFont("Helvetica",6.1)
    last_x=-1e10;last_y=-1e10
    for i in range(100):
        east=math.floor(x0/step)*step+i*step
        if east>x1+step:break
        x=xy(east,y0)[0]
        if left+4<=x<=left+width-4:
            pdf.setStrokeColor(GRID);pdf.line(x,bottom+14,x,bottom+height)
            label=f"{east:,.0f}"
            w=stringWidth(label,"Helvetica",6.1)
            if x-last_x>=w+12 and x-w/2>=left+4 and x+w/2<=left+width-4:
                pdf.setFillColor(GREEN);pdf.drawCentredString(x,bottom+4,label)
                last_x=x
    for i in range(100):
        north=math.floor(y0/step)*step+i*step
        if north>y1+step:break
        y=xy(x0,north)[1]
        if bottom+4<=y<=bottom+height-4:
            pdf.setStrokeColor(GRID);pdf.line(left+48,y,left+width,y)
            if y-last_y>=13:
                pdf.setFillColor(GREEN);pdf.drawString(left+3,y-2,f"{north:,.0f}")
                last_y=y
    pdf.restoreState()
    pdf.setStrokeColor(RULE);pdf.rect(left,bottom,width,height,fill=0,stroke=1)
    pdf.setFillColor(GREEN);pdf.setFont("Helvetica-Bold",7)
    pdf.drawString(left+4,bottom+height+5,
                   f"GRADE UTM  |  SIRGAS 2000  |  FUSO {zone}{hemi}")


def _coordinates_table(pdf, bounds, parcels, transformer, font_size, *, row_start=0, row_end=None):
    left,bottom,width,height=bounds
    rows=[
        (p.names[i],_dms(lon,"lon"),_dms(lat,"lat"),
         f"{transformer.transform(lon,lat)[0]:.3f}",
         f"{transformer.transform(lon,lat)[1]:.3f}",
         _br_number(p.altitudes[i],2) if p.altitudes[i] is not None else "—",
         _azimuth_minutes(seg["azimuth"]),
         _br_number(seg["distance"],2))
        for p in parcels
        for i,((lon,lat),seg) in enumerate(zip(p.points,p.segments))
    ]
    rows = rows[row_start:row_end]
    cols=_columns(width)
    pdf.saveState()
    pdf.setStrokeColor(RULE)
    pdf.setLineWidth(.45)
    pdf.rect(left,bottom,width,height,stroke=1,fill=0)
    top=bottom+height
    pdf.setFillColor(GREEN)
    pdf.rect(left,top-23,width,23,fill=1,stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold",9.3)
    pdf.drawString(left+7,top-15,"QUADRO DE COORDENADAS E SEGMENTOS")
    row_h=13 if font_size<=7 else 14
    header_y=top-23-row_h
    pdf.setFillColor(PALE)
    pdf.rect(left,header_y,width,row_h,fill=1,stroke=0)
    headings=("VÉRTICE","LONGITUDE","LATITUDE","ESTE (m)","NORTE (m)",
              "ALT. (m)","AZIMUTE","DIST. (m)")
    pdf.setFont("Helvetica-Bold",min(font_size,7))
    pdf.setFillColor(GREEN)
    for (offset,col_width),heading in zip(cols,headings):
        _fit_text(pdf,heading,col_width-5,"Helvetica-Bold",font_size)
        pdf.drawString(left+offset+3,header_y+3,heading)
    for i,row in enumerate(rows):
        y=header_y-(i+1)*row_h
        if i%2==0:
            pdf.setFillColor(colors.HexColor("#F8FAF8"))
            pdf.rect(left,y,width,row_h,fill=1,stroke=0)
        pdf.setStrokeColor(colors.HexColor("#E0E8E2"))
        pdf.line(left,y,left+width,y)
        pdf.setFillColor(DARK)
        for (offset,col_width),value in zip(cols,row):
            if not _fit_text(pdf,value,col_width-6,
                             "Helvetica",min(font_size,7.3),FONT_MIN):
                raise ValueError(
                    f"O texto '{value}' não cabe na coluna do quadro de coordenadas "
                    "com fonte legível. Escolha uma folha maior ou simplifique o dado."
                )
            pdf.drawString(left+offset+3,y+3,value)
    pdf.restoreState()


def _panel(pdf, x, top, width, limit, *, title, owner, owner_rg, owner_cpf,
           address, area, perimeter, zone, hemi, professional, image,
           image_source, stamp, show_situation=True, show_technical_stamp=True, compact=False):
    """Coluna direita: identificação, situação contígua, assinaturas em blocos."""
    pdf.setStrokeColor(RULE)
    if not compact:
        pdf.rect(x, limit, width, top-limit, stroke=1, fill=0)
    pdf.setFillColor(GREEN)
    pdf.rect(x, top-29, width, 29, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", min(9, max(6, width/22)))
    pdf.drawCentredString(x+width/2, top-19, "IDENTIFICAÇÃO DO IMÓVEL")
    y = top-29
    fields = [
        ("IMÓVEL", title),
        ("DETENTOR/POSSEIRO", owner or "Não informado"),
        ("CPF / RG", " | ".join(v for v in (owner_cpf,owner_rg) if v) or "Não informado"),
        ("LOCALIZAÇÃO", address or "Não informada"),
        ("ÁREA E PERÍMETRO", f"{_br_number(area,4)} ha | {_br_number(perimeter,2)} m"),
        ("DATUM / FUSO", f"SIRGAS 2000 - UTM {zone}{hemi}"),
    ]
    reserved = (148 if show_technical_stamp else 20) + (105 if show_situation else 0)
    available = y - limit - reserved
    measured = []
    for heading,value in fields:
        paragraph = Paragraph(
            escape(str(value or "Não informado")),
            ParagraphStyle("panelMeasure", fontName="Helvetica", fontSize=7.2, leading=9),
        )
        _, height = paragraph.wrap(max(35,width-15),500)
        measured.append(max(26,height+18))
    if sum(measured) > available:
        raise ValueError("A identificação excede a prancha. Escolha folha maior ou reduza textos.")
    for (heading,value),cell_h in zip(fields,measured):
        y = _cell(pdf,x,y,width,heading,value,cell_h)

    if show_situation:
        # A moldura começa imediatamente abaixo de seu título;
        # nunca centralizar o quadro dentro do espaço total da coluna.
        heading_y = y-12
        pdf.setFont("Helvetica-Bold", 8)
        pdf.setFillColor(GREEN)
        pdf.drawString(x+8,heading_y,"PLANTA DE SITUAÇÃO")
        frame_top = heading_y-8
        frame_width = width-14
        frame_height = frame_width*0.75
        frame_bottom = frame_top-frame_height
        if frame_bottom < limit+(135 if show_technical_stamp else 22):
            raise ValueError("Não há espaço para situação e assinaturas. Escolha papel maior.")
        pdf.setStrokeColor(RULE)
        pdf.rect(x+7,frame_bottom,frame_width,frame_height,stroke=1,fill=0)
        if image is not None:
            pdf.drawImage(image,x+10,frame_bottom+3,frame_width-6,frame_height-6,
                          preserveAspectRatio=True,anchor="c")
        pdf.setFont("Helvetica",5.6)
        pdf.setFillColor(DARK)
        pdf.drawString(x+8,frame_bottom-10,(image_source or "Base cartográfica")[:50])
        y=frame_bottom-15

    if show_technical_stamp:
        # Assinaturas sem desenhos de assinatura ou validação digital fictícia.
        box_top=y-5
        box_bottom=max(limit+23, box_top-175) if compact else limit+23
        if box_top-box_bottom < 110:
            raise ValueError("Espaço insuficiente para o quadro de assinaturas.")
        pdf.setStrokeColor(RULE)
        pdf.rect(x+7,box_bottom,width-14,box_top-box_bottom,stroke=1,fill=0)
        pdf.setFont("Helvetica-Bold",8)
        pdf.setFillColor(GREEN)
        pdf.drawString(x+11,box_top-12,"QUADRO DE ASSINATURAS")
        inner_width=width-28
        owner_lines=[owner or "Não informado"]
        if owner_rg: owner_lines.append(f"RG: {owner_rg}")
        if owner_cpf: owner_lines.append(f"CPF: {owner_cpf}")
        rt_lines=[
            professional.get("full_name") or "Não informado",
            professional.get("profession") or "",
            professional.get("specialization") or "",
            " | ".join(f"{k.upper()}: {professional[k]}" for k in ("cpf","rg")
                       if professional.get(k)),
            " | ".join(str(professional.get(k)) for k in
                       ("crea","visto","incra_code") if professional.get(k)),
            f"ART: {professional['art']}" if professional.get("art") else "",
        ]
        # Medir os parágrafos ANTES de desenhar ou de escolher a divisória.
        # Os blocos não recebem percentuais fixos porque CPF/RG e títulos
        # podem ocupar várias linhas.
        def measured_lines(lines, body_size):
            items=[]
            for index,line in enumerate(lines):
                if not line: continue
                size=body_size if index==0 else max(5.3,body_size-.5)
                p=Paragraph(
                    escape(str(line)),
                    ParagraphStyle("signature",fontName="Helvetica",fontSize=size,
                                   leading=size+1.5,alignment=1,textColor=DARK),
                )
                _,height=p.wrap(inner_width,300)
                items.append((p,height))
            return items
        # Reserva: título do quadro (17 pt), cada cabeçalho e traço
        # (17 pt), folgas de 3 pt e margem inferior (8 pt).
        area_height=box_top-box_bottom
        layout=None
        for font_size in (6.7,6.3,5.9,5.6):
            owner_items=measured_lines(owner_lines,font_size)
            rt_items=measured_lines(rt_lines,font_size)
            owner_needed=sum(h+2 for _,h in owner_items)+32
            rt_needed=sum(h+2 for _,h in rt_items)+25
            if owner_needed+rt_needed+22 <= area_height:
                layout=(owner_items,rt_items,owner_needed,rt_needed)
                break
        if layout is None:
            raise ValueError(
                "O quadro de assinaturas não comporta todos os dados com "
                "fontes legíveis. Escolha uma folha maior ou reduza os textos."
            )
        owner_items,rt_items,owner_needed,rt_needed=layout
        # A divisória nasce do tamanho real dos dados do proprietário.
        # Garante-se separação mínima da próxima seção.
        owner_heading=box_top-27
        def draw_group(heading,items,baseline,group_floor):
            pdf.setFillColor(DARK)
            pdf.setFont("Helvetica-Bold",6.5)
            pdf.drawString(x+13,baseline,heading)
            pdf.setStrokeColor(RULE)
            pdf.line(x+13,baseline-5,x+width-13,baseline-5)
            cursor=baseline-15
            for paragraph,height in items:
                bottom=cursor-height
                if bottom < group_floor+5:
                    raise ValueError(
                        "O quadro de assinaturas não possui espaço suficiente "
                        "para distribuir os textos sem sobreposição."
                    )
                paragraph.drawOn(pdf,x+14,bottom)
                cursor=bottom-2
            return cursor
        owner_floor=box_top-17-owner_needed
        if owner_floor-box_bottom < rt_needed+8:
            raise ValueError("Espaço insuficiente para assinaturas. Use folha maior.")
        draw_group("PROPRIETÁRIO / DETENTOR",owner_items,owner_heading,owner_floor)
        pdf.setStrokeColor(RULE)
        pdf.line(x+7,owner_floor,x+width-7,owner_floor)
        draw_group("RESPONSÁVEL TÉCNICO",rt_items,owner_floor-12,box_bottom)

    pdf.setFillColor(DARK)
    pdf.setFont("Helvetica",5.6)
    pdf.drawString(x+7,(box_bottom-9 if show_technical_stamp and compact else limit+7),stamp[:55])


def _memorial_pdf(pdf, parcels, property_name, owner, owner_rg, owner_cpf,
                  address, heading, professional, croqui, stamp, edited_memorial=None, property_metadata=None):
    w,h=A4; margin=43
    body=ParagraphStyle(
        "memorial",fontName="Helvetica",fontSize=9.4,leading=14.2,
        alignment=4,textColor=DARK,spaceAfter=0,
    )
    page_no=0
    def foot():
        pdf.setStrokeColor(GRID)
        pdf.line(margin,66,w-margin,66)
        pdf.setFillColor(DARK)
        if croqui:
            caveat=Paragraph(escape(DISCLAIMER),ParagraphStyle(
                "caveat",fontName="Helvetica",fontSize=6.5,leading=8,
                textColor=colors.HexColor("#8C3C2A"),
            ))
            _,ch=caveat.wrap(w-2*margin,55)
            caveat.drawOn(pdf,margin,55-ch)
        pdf.setFont("Helvetica",6.8)
        pdf.drawRightString(w-margin,20,f"{stamp} | Fl. {page_no}")
    def heading_block():
        pdf.setPageSize(A4)
        pdf.setFillColor(GREEN)
        pdf.rect(margin,h-75,w-2*margin,3,fill=1,stroke=0)
        pdf.setFillColor(DARK);pdf.setFont("Helvetica-Bold",15)
        pdf.drawCentredString(w/2,h-44,heading[:56].upper())
        pdf.setFont("Helvetica-Bold",10.5)
        pdf.drawCentredString(w/2,h-62,property_name[:68].upper())
        pdf.setFont("Helvetica",7)
        pdf.setFillColor(colors.HexColor("#58736A"))
        pdf.drawCentredString(w/2,h-85,"PEÇA TÉCNICA  •  DADOS E DESCRIÇÃO PERIMETRAL")
    def next_page():
        nonlocal y,page_no
        if page_no:foot();pdf.showPage()
        page_no+=1
        heading_block()
        y=h-105
    next_page()
    def paragraph(text,bold=False,space=4):
        nonlocal y
        raw=escape(text)
        if bold:
            raw=f"<b>{raw}</b>"
        pending=Paragraph(raw,body)
        page_width=w-2*margin
        while True:
            available=y-91-space
            if available < body.leading*2:
                next_page()
                available=y-91-space
            pieces=pending.split(page_width,available)
            if not pieces:
                if abs(y-(h-93))<1:
                    raise ValueError("Trecho do memorial excede a área imprimível.")
                next_page()
                continue
            first=pieces[0]
            _,height=first.wrap(page_width,available)
            first.drawOn(pdf,margin,y-height)
            y-=height
            if len(pieces)==1:
                y-=space
                break
            next_page()
            pending=pieces[1]
    # Texto aprovado pelo usuário tem precedência sobre a versão automática.
    # A edição não altera cálculos geométricos ou o carimbo da primeira folha.
    if edited_memorial is not None:
        for line in edited_memorial.splitlines():
            value=line.strip()
            if not value:
                y-=5
                continue
            paragraph(value, bold=value.isupper() and len(value)<110, space=4)
        foot()
        return
    # Tabela compacta de identificação e metragem.
    meta=[
        f"IMÓVEL: {property_name}",
        f"DETENTOR/POSSEIRO: {owner or 'Não informado'}",
        f"CPF: {owner_cpf or '—'}     RG: {owner_rg or '—'}",
        f"LOCALIZAÇÃO: {address or 'Não informada'}",
        f"ÁREA: {_br_number(sum(p.area_ha for p in parcels),4)} ha    "
        f"PERÍMETRO: {_br_number(sum(p.perimeter for p in parcels),2)} m",
    ]
    for key, label in (
        ("legal_status", "SITUAÇÃO JURÍDICA"),
        ("area_nature", "NATUREZA DA ÁREA"),
        ("sncr", "SNCR/INCRA"),
        ("cns", "CNS"),
        ("registration", "MATRÍCULA"),
    ):
        val = (property_metadata or {}).get(key)
        if val:
            meta.append(f"{label}: {val[:250]}")
    # Identificação em seção única, evitando cabeçalho isolado.
    pdf.setFillColor(GREEN)
    pdf.roundRect(margin,y-21,w-2*margin,20,3,stroke=0,fill=1)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold",8.4)
    pdf.drawString(margin+9,y-15,"01  IDENTIFICAÇÃO CADASTRAL DO IMÓVEL")
    y-=32
    for line in meta:
        paragraph(line,bold=line.startswith("IMÓVEL"),space=2)
    y-=8
    prose=build_joint_memorial(
        parcels,title=property_name,owner=owner,
        responsible=professional.get("full_name"),croqui=False,
        owner_rg=owner_rg,owner_cpf=owner_cpf,property_address=address,
        professional=professional,memorial_heading=heading,
    )
    start=prose.find("DESCRIÇÃO DO PERÍMETRO")
    end=prose.find("________________________________________")
    for line in prose[max(start,0):end if end>=0 else None].splitlines():
        line=line.strip()
        if not line:continue
        if line.startswith("DESCRIÇÃO DO PERÍMETRO"):
            if y<165:next_page()
            y-=4
            pdf.setFillColor(GREEN)
            pdf.roundRect(margin,y-24,w-2*margin,21,3,fill=1,stroke=0)
            pdf.setFillColor(colors.white)
            pdf.setFont("Helvetica-Bold",8.4)
            pdf.drawString(margin+9,y-18,"02  DESCRIÇÃO TÉCNICA DO PERÍMETRO")
            y-=34
            paragraph(line,bold=True,space=9)
        else:
            paragraph(line,space=4)
    if y<190:next_page()
    y-=22
    pdf.setStrokeColor(DARK);pdf.line(margin+100,y,w-margin-100,y)
    y-=15
    lines=[
        professional.get("full_name") or "Responsável técnico",
        " | ".join(str(professional.get(k) or "")
                 for k in ("profession","crea","visto") if professional.get(k)),
    ]
    if professional.get("art"):
        lines.append(f"ART: {professional['art']}")
    for i,line in enumerate(lines):
        pdf.setFillColor(DARK)
        pdf.setFont("Helvetica-Bold" if i==0 else "Helvetica",9 if i==0 else 8)
        pdf.drawCentredString(w/2,y,line[:92]);y-=13
    foot()


def make_joint_pdf(*, parcels: list[Parcel], title: str,
                   owner_name: str | None, responsible_name: str | None, croqui: bool,
                   raster_b64: str | None, raster_source: str | None,
                   owner_rg: str | None=None, owner_cpf: str | None=None,
                   property_address: str | None=None,
                   plant_heading: str="PLANTA GEORREFERENCIADA",
                   memorial_heading: str="MEMORIAL DESCRITIVO",
                   professional: dict | None=None, qr_url: str | None=None,
                   paper_format: str | None="A4",
                   scale_denominator: int | None=None,
                   orientation: str = "paisagem",
                   plant_elements: dict | None = None,
                   magnetic_declination_degrees: float | None = None,
                   edited_memorial: str | None = None,
                   survey_date: str | None = None,
                   property_metadata: dict[str, str] | None = None,
                   layout_template: str = 'lateral') -> tuple[bytes,str,int]:
    elements = plant_elements or {}
    enabled = lambda key: elements.get(key, True)
    if enabled("situation") and not raster_b64:
        raise ValueError("A Planta de Situação exige imagem raster capturada do mapa.")
    if not parcels:
        raise ValueError("Selecione ao menos um polígono.")
    professional=dict(professional or {})
    if responsible_name and not professional.get("full_name"):
        professional["full_name"]=responsible_name
    raster=_raster_reader(raster_b64) if raster_b64 else None
    reference_dt = datetime.now(ZoneInfo("America/Belem")).date()
    if survey_date:
        from datetime import date
        reference_dt=date.fromisoformat(survey_date)
    stamp=datetime.now(ZoneInfo("America/Belem")).strftime(
        "%d/%m/%Y %H:%M:%S - Horário de Belém"
    )
    all_vertices=[pt for parcel in parcels for pt in parcel.points]
    mid_lon=sum(p[0] for p in all_vertices)/len(all_vertices)
    mid_lat=sum(p[1] for p in all_vertices)/len(all_vertices)
    zone=max(1,min(60,int((mid_lon+180)//6)+1))
    hemi="S" if mid_lat<0 else "N"
    crs=CRS.from_proj4(
        f"+proj=utm +zone={zone} {'+south' if hemi=='S' else ''} "
        "+ellps=GRS80 +units=m +no_defs"
    )
    transformer=Transformer.from_crs("EPSG:4674",crs,always_xy=True)
    projected=[[transformer.transform(*pt) for pt in parcel.points]
               for parcel in parcels]
    count=sum(len(p.points) for p in parcels)
    if layout_template in ("classic_lateral", "cartographic_frame", "modern_lateral"):
        from app.services.plant_template_engine import render_professional_plant
        buffer = io.BytesIO()
        printer = canvas.Canvas(buffer, pagesize=portrait(PAPERS[(paper_format or "A2").upper()]),
                                pageCompression=1)
        printer.setTitle(f"{plant_heading} — {title}")
        _, _, selected_scale = render_professional_plant(
            printer, parcels=parcels, title=title, owner_name=owner_name,
            owner_rg=owner_rg, owner_cpf=owner_cpf, property_address=property_address,
            professional=professional, raster=raster, raster_source=raster_source,
            paper_format=(paper_format or "A2").upper(), orientation=orientation,
            scale_denominator=scale_denominator, plant_elements=elements,
            stamp=stamp, croqui=croqui, disclaimer=DISCLAIMER,
            layout_template=layout_template, property_metadata=property_metadata,
        )
        printer.showPage()
        _memorial_pdf(
            printer, parcels, title, owner_name, owner_rg, owner_cpf,
            property_address, memorial_heading, professional, croqui, stamp,
            edited_memorial, property_metadata=property_metadata,
        )
        printer.save()
        return buffer.getvalue(), (paper_format or "A2").upper(), selected_scale

    fmt,w,h,side,bounds,viewport,table_rect,scale=_layout(
        projected,vertex_count=count,paper=paper_format,
        orientation=orientation,scale=scale_denominator,
        show_coordinates=enabled("coordinates"),
        layout_template=layout_template,
    )
    x0,y0,x1,y1=bounds
    vx,vy,vw,vh=viewport
    f=_pt_per_meter(scale)
    px=vx+(vw-(x1-x0)*f)/2
    py=vy+(vh-(y1-y0)*f)/2
    def xy(e,n):
        return (px+(e-x0)*f,py+(n-y0)*f)
    data=io.BytesIO()
    pdf=canvas.Canvas(data,pagesize=(w,h),pageCompression=1)
    pdf.setTitle(f"{plant_heading} — {title}")
    pdf.setStrokeColor(DARK);pdf.setLineWidth(.8)
    pdf.rect(23,23,w-46,h-46,fill=0,stroke=1)
    if enabled("title"):
        pdf.setFillColor(GREEN);pdf.setFont("Helvetica-Bold",13)
        pdf.drawCentredString((38+side-15)/2,h-43,plant_heading[:65].upper())
        pdf.setFillColor(DARK);pdf.setFont("Helvetica-Bold",10)
        pdf.drawCentredString((38+side-15)/2,h-59,title[:70].upper())
    pdf.setStrokeColor(RULE)
    pdf.line(38,h-69,side-15,h-69)
    # Grade contida rigorosamente na moldura cartográfica.
    if enabled("grid"):
        _grid(pdf,viewport,bounds,xy,zone,hemi)
    else:
        pdf.setStrokeColor(RULE)
        pdf.rect(*viewport,fill=0,stroke=1)
    label_layout=LabelLayout(viewport)
    label_layout.reserved.append(Box(vx,vy,55,vh))
    label_layout.reserved.append(Box(vx,vy,vw,16))
    orientation_on = enabled("north")
    # Símbolos discretos em cantos da moldura, com áreas de exclusão
    # para etiquetas; nunca redesenhar uma faixa adicional inteira.
    rose_box=Box(vx+58,vy+vh-50,44,43)
    magnetic_box=Box(vx+vw-100,vy+vh-50,94,43)
    if orientation_on:
        # Não permitir símbolos sobre a geometria, mesmo para parcelas
        # que ocupem grande parte da folha.
        for ring in projected:
            screen=[xy(*p) for p in ring]
            occupied=Box(min(p[0] for p in screen)-6,
                         min(p[1] for p in screen)-6,
                         max(p[0] for p in screen)-min(p[0] for p in screen)+12,
                         max(p[1] for p in screen)-min(p[1] for p in screen)+12)
            if rose_box.intersects(occupied, gap=2) or magnetic_box.intersects(occupied,gap=2):
                raise ValueError("Símbolos de orientação encontram o polígono. "
                                 "Escolha folha maior ou ajuste a escala da planta.")
        label_layout.reserved.extend([rose_box, magnetic_box])
    palette=(colors.HexColor("#276749"),colors.HexColor("#1E6290"),
             colors.HexColor("#8E7235"),colors.HexColor("#85528D"))
    for index,(parcel,ring) in enumerate(zip(parcels,projected)):
        points=[xy(*v) for v in ring]
        cx=sum(x for x,_ in points)/len(points)
        cy=sum(y for _,y in points)/len(points)
        pdf.saveState()
        _clip_rect(pdf,*viewport)
        boundary=pdf.beginPath()
        boundary.moveTo(*points[0])
        for point in points[1:]:boundary.lineTo(*point)
        boundary.close()
        pdf.setFillColor(colors.HexColor("#E5F0E6"))
        pdf.setStrokeColor(palette[index % len(palette)])
        pdf.setLineWidth(1.7)
        pdf.drawPath(boundary,stroke=1,fill=1)
        for x,y in points:
            pdf.setFillColor(colors.white)
            pdf.setStrokeColor(DARK)
            pdf.circle(x,y,2.7,fill=1,stroke=1)
        pdf.restoreState()
        if enabled("vertex_labels"):
            for i,(x,y) in enumerate(points):
                label_layout.place(pdf,[parcel.names[i]],(x,y),
                    desired=7.2,minimum=6.0,
                    offsets=[(12,13),(-12,13),(12,-13),(-12,-13),
                             (22,7),(-22,7)])
        for i,point in enumerate(points):
            _azimuth_and_distance(
                pdf,point,points[(i+1)%len(points)],
                parcel.segments[i],parcel.confrontants[i],(cx,cy),viewport,
                layout=label_layout,show_azimuth=enabled("azimuths"),
                show_distance=enabled("distances"),
                show_confrontants=enabled("confrontants"))
    # Os três elementos de escala ocupam uma faixa independente abaixo
    # do quadro UTM; não interferem nos valores das coordenadas.
    footer_y = vy-25
    if enabled("scale_text"):
        pdf.setFillColor(DARK)
        pdf.setFont("Helvetica-Bold",7.0)
        pdf.drawString(vx+4,footer_y,f"ESCALA 1:{scale:,}".replace(",","."))
    if elements.get("scale_bar",False):
        bar_pt=min(vw*.28,90)
        bar_m=bar_pt/_pt_per_meter(scale)
        bx=vx+vw-bar_pt-13
        by=footer_y+2
        pdf.saveState()
        pdf.setStrokeColor(GREEN)
        pdf.setFillColor(GREEN)
        pdf.rect(bx,by,bar_pt/2,5,stroke=1,fill=1)
        pdf.setFillColor(colors.white)
        pdf.rect(bx+bar_pt/2,by,bar_pt/2,5,stroke=1,fill=1)
        pdf.setFont("Helvetica",6)
        pdf.setFillColor(DARK)
        pdf.drawString(bx,by-9,"0")
        pdf.drawRightString(bx+bar_pt,by-9,f"{bar_m:.1f} m")
        pdf.restoreState()

    if orientation_on:
        from pyproj import Proj
        from calendar import isleap
        longitude,latitude=max(all_vertices,key=lambda pt:pt[1])
        convergence=float(Proj(crs).get_factors(longitude,latitude).meridian_convergence)
        declination=None
        magnetic_source="Não selecionada"
        if elements.get("magnetic_declination",False):
            if magnetic_declination_degrees is not None:
                declination=float(magnetic_declination_degrees)
                magnetic_source="Informada pelo RT"
            else:
                from pygeomag import GeoMag
                days=366 if isleap(reference_dt.year) else 365
                decimal_year=reference_dt.year+(reference_dt.timetuple().tm_yday-1)/days
                if not 2025 <= decimal_year < 2030:
                    raise ValueError("WMM2025 exige data de referência entre 2025 e 2029.")
                declination=float(GeoMag(coefficients_file="wmm/WMM_2025.COF").calculate(
                    glat=latitude,glon=longitude,alt=0,time=decimal_year).d)
                magnetic_source="WMM2025 (alt. 0 km)"
        # Rosa do norte (canto superior esquerdo), discreta e sem moldura.
        pdf.saveState()
        pdf.setFillColor(colors.white)
        pdf.rect(rose_box.x,rose_box.y,rose_box.w,rose_box.h,fill=1,stroke=0)
        cx=rose_box.x+rose_box.w/2
        cy=rose_box.y+17
        pdf.setStrokeColor(DARK)
        pdf.setFillColor(DARK)
        pdf.setLineWidth(.65)
        for degrees in range(0,360,45):
            angle=math.radians(degrees)
            reach=14 if degrees%90==0 else 9
            pdf.line(cx,cy,cx+math.sin(angle)*reach,cy+math.cos(angle)*reach)
        pdf.setFont("Helvetica-Bold",6.7)
        pdf.drawCentredString(cx,rose_box.y+35,"N")
        # Declinação e convergência em ícone compacto no canto oposto.
        pdf.setFillColor(colors.white)
        pdf.rect(magnetic_box.x,magnetic_box.y,magnetic_box.w,magnetic_box.h,
                 fill=1,stroke=0)
        mx=magnetic_box.x+16
        my=magnetic_box.y+9
        pdf.setStrokeColor(DARK)
        pdf.setLineWidth(.7)
        for ang,reach in [(0,23),(convergence,20)]+(
                [(declination,18)] if declination is not None else []):
            rad=math.radians(ang)
            pdf.line(mx,my,mx+math.sin(rad)*reach,my+math.cos(rad)*reach)
        pdf.setFont("Helvetica",5.5)
        pdf.setFillColor(GREEN)
        pdf.drawString(magnetic_box.x+34,magnetic_box.y+30,"NG / NQ / NM")
        pdf.setFillColor(DARK)
        pdf.drawString(magnetic_box.x+34,magnetic_box.y+22,
                       f"c {convergence:+.4f}°")
        pdf.drawString(magnetic_box.x+34,magnetic_box.y+14,
                       f"d {declination:+.3f}°" if declination is not None
                       else "d: não informada")
        pdf.setFont("Helvetica",5.0)
        source_short=("WMM2025" if magnetic_source.startswith("WMM2025")
                      else "RT" if declination is not None else "—")
        pdf.drawString(magnetic_box.x+34,magnetic_box.y+6,
                       source_short+" "+reference_dt.strftime("%d/%m/%y"))
        pdf.restoreState()
    if enabled('coordinates'):
        _coordinates_table(pdf,table_rect,parcels,transformer,6.8 if fmt=='A4' else 7.3,
                           row_end=8 if layout_template=='inferior' else None)
    # Coluna direita em células separadas com situação cartográfica.
    panel_x=side+7
    _panel(
        pdf,panel_x,h-28,w-panel_x-28,
        (42+table_rect[3]+10) if layout_template=='inferior' and enabled('coordinates') else 28,
        title=title,owner=owner_name,owner_rg=owner_rg,owner_cpf=owner_cpf,
        address=property_address,
        area=sum(p.area_ha for p in parcels),
        perimeter=sum(p.perimeter for p in parcels),
        zone=zone,hemi=hemi,professional=professional,
        image=raster,image_source=raster_source,stamp=stamp,
        show_situation=enabled("situation"),
        show_technical_stamp=enabled("technical_stamp"),
        compact=layout_template=='inferior',
    )
    if croqui:
        warning=Paragraph(
            escape(DISCLAIMER),
            ParagraphStyle("plant_warning",fontName="Helvetica",fontSize=5.8,
                           leading=6.5,textColor=colors.HexColor("#8A3125")),
        )
        _,warning_height=warning.wrap(side-54,30)
        if warning_height>16:
            raise ValueError("A observação de croqui não cabe no rodapé deste formato.")
        warning.drawOn(pdf,38,40-warning_height)
    pdf.showPage()
    if layout_template == 'inferior' and enabled('coordinates') and count > 8:
        row_h = 13 if fmt in ('A4', 'A3') else 14
        max_rows = max(1, int((h - 145 - 30) / row_h))
        remaining = count - 8
        pages = math.ceil(remaining / max_rows)
        rows_per_page = math.ceil(remaining / pages)
        for first in range(8, count, rows_per_page):
            last = min(count, first + max_rows)
            subset = last - first
            pdf.setPageSize((w, h))
            pdf.setStrokeColor(DARK)
            pdf.rect(23, 23, w-46, h-46, fill=0, stroke=1)
            pdf.setFont('Helvetica-Bold', 11)
            pdf.setFillColor(GREEN)
            pdf.drawString(38, h-44, f'QUADRO DE COORDENADAS — {title[:65]}')
            pdf.setFont('Helvetica', 7)
            pdf.setFillColor(DARK)
            pdf.drawString(38, h-59, f'Continuação: vértices {first+1} a {last} de {count}')
            table_height = 23 + (subset+1)*row_h + 7
            _coordinates_table(pdf, (38, h-90-table_height, w-76, table_height),
                               parcels, transformer, 7.0, row_start=first, row_end=last)
            pdf.showPage()
    _memorial_pdf(
        pdf,parcels,title,owner_name,owner_rg,owner_cpf,property_address,
        memorial_heading,professional,croqui,stamp,edited_memorial,
        property_metadata=property_metadata,
    )
    pdf.save()
    return data.getvalue(),fmt,scale
