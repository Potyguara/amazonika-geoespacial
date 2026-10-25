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


def _layout(projected, *, vertex_count, paper, orientation, scale):
    fmt = (paper or "A4").upper()
    if fmt not in PAPERS:
        raise ValueError("Formato inválido. Escolha A4, A3, A2, A1 ou A0.")
    if orientation not in ("paisagem", "retrato"):
        raise ValueError("Orientação inválida. Escolha paisagem ou retrato.")
    w, h = (landscape if orientation == "paisagem" else portrait)(PAPERS[fmt])
    frame = (23, 23, w-46, h-46)
    side_x = w * (.73 if orientation == "paisagem" else .68)
    map_left, map_right = 38, side_x - 15
    available_width = map_right - map_left
    row_h = 13 if fmt in ("A4", "A3") else 14
    title_h = 23
    table_h = title_h + (vertex_count + 1) * row_h + 7
    map_bottom = 42 + table_h + 13
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
    return (fmt, w, h, side_x, bounds,
            (map_left, map_bottom, map_w, map_h), (38, 42, map_w, table_h), chosen)


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


def _azimuth_and_distance(pdf, p0, p1, row, confrontant, inner_point, viewport):
    x0,y0 = p0
    x1,y1 = p1
    dx,dy = x1-x0,y1-y0
    length = math.hypot(dx,dy)
    if length < 1:
        return
    angle = math.degrees(math.atan2(dy,dx))
    ux,uy = dx/length,dy/length
    nx,ny = -uy,ux
    mx,my = (x0+x1)/2,(y0+y1)/2
    # Texto do confrontante para o lado interno da poligonal.
    cx,cy = inner_point
    if (cx-mx)*nx + (cy-my)*ny < 0:
        nx,ny = -nx,-ny
    # Textos permanecem legíveis, sem ficar de cabeça para baixo.
    if abs(angle) > 90:
        angle = (angle+180) % 360
        ux,uy = -ux,-uy
    pdf.saveState()
    _clip_rect(pdf,*viewport)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold",7.0)
    distance = f"{_br_number(row['distance'],2)} m"
    azimuth = _azimuth_minutes(row["azimuth"])
    # Distância e azimute em posições diferentes ao longo do mesmo lado.
    # Para lados muito curtos, abrevia a fonte, mas não altera os valores.
    for text, position, offset in ((distance,.28,9),(azimuth,.73,9)):
        if stringWidth(text,"Helvetica-Bold",7) > length*.46:
            offset += 10
        tx = x0+dx*position+nx*offset
        ty = y0+dy*position+ny*offset
        pdf.saveState()
        pdf.translate(tx,ty)
        pdf.rotate(angle)
        pdf.setFillColor(colors.white)
        ww=stringWidth(text,"Helvetica-Bold",7)
        pdf.rect(-ww/2-2,-2,ww+4,11,fill=1,stroke=0)
        pdf.setFillColor(DARK)
        pdf.drawCentredString(0,0,text)
        pdf.restoreState()
    if confrontant.strip():
        ctext = confrontant.strip()
        if len(ctext)>45:
            ctext = ctext[:42]+"…"
        font = 7.0
        pdf.setFont("Helvetica-Bold",font)
        while font>5.8 and stringWidth(ctext,"Helvetica-Bold",font)>length*.95:
            font -= .3
        tx = mx+nx*27
        ty = my+ny*27
        pdf.saveState()
        pdf.translate(tx,ty)
        pdf.rotate(angle)
        pdf.setFont("Helvetica-Bold",font)
        ww=stringWidth(ctext,"Helvetica-Bold",font)
        pdf.setFillColor(colors.white)
        pdf.rect(-ww/2-2,-2,ww+4,font+4,fill=1,stroke=0)
        pdf.setFillColor(GREEN)
        pdf.drawCentredString(0,0,ctext)
        pdf.restoreState()
    pdf.restoreState()


def _grid(pdf, viewport, bounds, xy, zone, hemi):
    left,bottom,width,height = viewport
    x0,y0,x1,y1 = bounds
    span=max(x1-x0,y1-y0,1)
    step=10**math.floor(math.log10(max(span/5,1)))
    if span/step>8: step*=2
    if span/step<3: step/=2
    pdf.saveState()
    _clip_rect(pdf,left,bottom,width,height)
    pdf.setStrokeColor(GRID)
    pdf.setLineWidth(.5)
    pdf.setFont("Helvetica",6)
    pdf.setFillColor(GREEN)
    for i in range(100):
        east=math.floor(x0/step)*step+i*step
        if east>x1+step: break
        x=xy(east,y0)[0]
        if left<=x<=left+width:
            pdf.line(x,bottom,x,bottom+height)
            pdf.drawCentredString(x, bottom+6, f"{east:,.0f}")
    for i in range(100):
        north=math.floor(y0/step)*step+i*step
        if north>y1+step: break
        y=xy(x0,north)[1]
        if bottom<=y<=bottom+height:
            pdf.line(left,y,left+width,y)
            pdf.drawString(left+4,y+2,f"{north:,.0f}")
    pdf.restoreState()
    pdf.setStrokeColor(RULE)
    pdf.rect(left,bottom,width,height,fill=0,stroke=1)
    pdf.setFillColor(GREEN);pdf.setFont("Helvetica-Bold",7)
    pdf.drawString(left+4,bottom+height+5, f"GRADE UTM  |  SIRGAS 2000  |  FUSO {zone}{hemi}")


def _coordinates_table(pdf, bounds, parcels, transformer, font_size):
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
                # Nome longo deve ser editado pelo usuário antes da emissão.
                if offset == 0.:
                    raise ValueError(
                        f"Código de vértice '{value}' não cabe na tabela; "
                        "reduza seu comprimento ou escolha papel maior."
                    )
            pdf.drawString(left+offset+3,y+3,value)
    pdf.restoreState()


def _panel(pdf, x, top, width, limit, *, title, owner, owner_rg, owner_cpf,
           address, area, perimeter, zone, hemi, professional, image,
           image_source, stamp):
    pdf.setStrokeColor(RULE);pdf.rect(x,limit,width,top-limit,stroke=1,fill=0)
    pdf.setFillColor(GREEN);pdf.rect(x,top-32,width,32,fill=1,stroke=0)
    pdf.setFillColor(colors.white);pdf.setFont("Helvetica-Bold",10)
    pdf.drawCentredString(x+width/2,top-20,"IDENTIFICAÇÃO DO IMÓVEL")
    y=top-32
    fields=[
        ("IMÓVEL",title),
        ("DETENTOR/POSSEIRO",owner or "Não informado"),
        ("CPF / RG", " | ".join(x for x in (owner_cpf,owner_rg) if x) or "Não informado"),
        ("LOCALIZAÇÃO",address or "Não informada"),
        ("ÁREA E PERÍMETRO",f"{_br_number(area,4)} ha  |  {_br_number(perimeter,2)} m"),
        ("DATUM / FUSO",f"SIRGAS 2000 — UTM {zone}{hemi}"),
        ("RESPONSÁVEL TÉCNICO",professional.get("full_name") or "Não informado"),
        ("CREA / VISTO / ART"," | ".join(
             str(professional.get(k) or "") for k in ("crea","visto","art")
             if professional.get(k)) or "Não informado"),
    ]
    available=(top-32)-(limit+138)
    heights=[]
    for heading,value in fields:
        measure=Paragraph(
            escape(str(value or "Não informado")),
            ParagraphStyle("cellMeasure",fontName="Helvetica",fontSize=7.6,leading=9.5),
        )
        _,text_height=measure.wrap(max(35,width-15),500)
        heights.append(max(27,text_height+19))
    if sum(heights)>available:
        raise ValueError(
            "Os dados cadastrais não cabem na coluna de identificação. "
            "Use papel maior ou reduza o texto dos campos."
        )
    for (heading,value),cell_h in zip(fields,heights):
        y=_cell(pdf,x,y,width,heading,value,cell_h)
    # Raster dentro de moldura, sem título 'raster do mapa'.
    raster_bottom=limit+29
    raster_h=y-raster_bottom-17
    if raster_h<65:
        raise ValueError("Falta espaço para a Planta de Situação; escolha papel maior.")
    pdf.setFont("Helvetica-Bold",8)
    pdf.setFillColor(GREEN)
    pdf.drawString(x+8,y-12,"PLANTA DE SITUAÇÃO")
    pdf.setStrokeColor(RULE)
    pdf.rect(x+7,raster_bottom,width-14,raster_h,stroke=1,fill=0)
    pdf.drawImage(image,x+10,raster_bottom+3,width-20,raster_h-6,
                  preserveAspectRatio=True,anchor="c")
    pdf.setFont("Helvetica",6.4)
    pdf.setFillColor(DARK)
    pdf.drawString(x+7,limit+16,(image_source or "Base de referência")[:47])
    pdf.drawString(x+7,limit+5,stamp[:60])


def _memorial_pdf(pdf, parcels, property_name, owner, owner_rg, owner_cpf,
                  address, heading, professional, croqui, stamp):
    w,h=A4; margin=43
    body=ParagraphStyle(
        "memorial",fontName="Helvetica",fontSize=9.4,leading=14,
        alignment=4,textColor=DARK,
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
        pdf.setFillColor(DARK);pdf.setFont("Helvetica-Bold",15)
        pdf.drawCentredString(w/2,h-46,heading[:56].upper())
        pdf.setFont("Helvetica-Bold",10.5)
        pdf.drawCentredString(w/2,h-63,property_name[:68].upper())
        pdf.setStrokeColor(GREEN)
        pdf.line(margin,h-74,w-margin,h-74)
    def next_page():
        nonlocal y,page_no
        if page_no:foot();pdf.showPage()
        page_no+=1
        heading_block()
        y=h-93
    next_page()
    def paragraph(text,bold=False,space=4):
        nonlocal y
        raw=escape(text)
        if bold:raw=f"<b>{raw}</b>"
        p=Paragraph(raw,body)
        _,height=p.wrap(w-2*margin,2000)
        if y-height-space < 91:
            next_page()
        p.drawOn(pdf,margin,y-height)
        y-=height+space
    # Tabela compacta de identificação e metragem.
    meta=[
        f"IMÓVEL: {property_name}",
        f"DETENTOR/POSSEIRO: {owner or 'Não informado'}",
        f"CPF: {owner_cpf or '—'}     RG: {owner_rg or '—'}",
        f"LOCALIZAÇÃO: {address or 'Não informada'}",
        f"ÁREA: {_br_number(sum(p.area_ha for p in parcels),4)} ha    "
        f"PERÍMETRO: {_br_number(sum(p.perimeter for p in parcels),2)} m",
    ]
    for line in meta:paragraph(line,bold=line.startswith("IMÓVEL"),space=2)
    y-=10
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
            y-=7
            paragraph(line,bold=True,space=8)
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
                   orientation: str = "paisagem") -> tuple[bytes,str,int]:
    if not raster_b64:
        raise ValueError("A Planta de Situação exige imagem raster capturada do mapa.")
    if not parcels:
        raise ValueError("Selecione ao menos um polígono.")
    professional=dict(professional or {})
    if responsible_name and not professional.get("full_name"):
        professional["full_name"]=responsible_name
    raster=_raster_reader(raster_b64)
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
    fmt,w,h,side,bounds,viewport,table_rect,scale=_layout(
        projected,vertex_count=count,paper=paper_format,
        orientation=orientation,scale=scale_denominator,
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
    pdf.setFillColor(GREEN);pdf.setFont("Helvetica-Bold",13)
    pdf.drawCentredString((38+side-15)/2,h-43,plant_heading[:65].upper())
    pdf.setFillColor(DARK);pdf.setFont("Helvetica-Bold",10)
    pdf.drawCentredString((38+side-15)/2,h-59,title[:70].upper())
    pdf.setStrokeColor(RULE)
    pdf.line(38,h-69,side-15,h-69)
    # Grade contida rigorosamente na moldura cartográfica.
    _grid(pdf,viewport,bounds,xy,zone,hemi)
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
        for i,point in enumerate(points):
            _azimuth_and_distance(pdf,point,points[(i+1)%len(points)],
                                  parcel.segments[i],parcel.confrontants[i],
                                  (cx,cy),viewport)
            x,y=point
            pdf.saveState();_clip_rect(pdf,*viewport)
            pdf.setFont("Helvetica-Bold",7)
            label=parcel.names[i]
            txtw=stringWidth(label,"Helvetica-Bold",7)
            lx=max(vx+4,min(vx+vw-txtw-5,x+5))
            ly=max(vy+5,min(vy+vh-13,y+8))
            pdf.setFillColor(colors.white)
            pdf.rect(lx-2,ly-2,txtw+4,10,fill=1,stroke=0)
            pdf.setFillColor(DARK);pdf.drawString(lx,ly,label)
            pdf.restoreState()
    # Norte permanece dentro da grade, sem invadir os rótulos externos.
    pdf.setStrokeColor(GREEN);pdf.setLineWidth(1.5)
    nx,ny=vx+18,vy+vh-18
    pdf.line(nx,ny-22,nx,ny)
    pdf.line(nx,ny,nx-5,ny-7);pdf.line(nx,ny,nx+5,ny-7)
    pdf.setFont("Helvetica-Bold",8);pdf.drawCentredString(nx,ny+5,"N")
    pdf.setFillColor(DARK);pdf.setFont("Helvetica",7.5)
    pdf.drawString(vx,vy-13,f"ESCALA 1:{scale:,}  |  FOLHA {fmt} ({orientation})")
    # Quadro de coordenadas *na mesma folha*, independente do volume.
    _coordinates_table(pdf,table_rect,parcels,transformer,6.8 if fmt=="A4" else 7.3)
    # Coluna direita em células separadas com situação cartográfica.
    panel_x=side+7
    _panel(
        pdf,panel_x,h-28,w-panel_x-28,28,
        title=title,owner=owner_name,owner_rg=owner_rg,owner_cpf=owner_cpf,
        address=property_address,
        area=sum(p.area_ha for p in parcels),
        perimeter=sum(p.perimeter for p in parcels),
        zone=zone,hemi=hemi,professional=professional,
        image=raster,image_source=raster_source,stamp=stamp,
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
    _memorial_pdf(
        pdf,parcels,title,owner_name,owner_rg,owner_cpf,property_address,
        memorial_heading,professional,croqui,stamp,
    )
    pdf.save()
    return data.getvalue(),fmt,scale
