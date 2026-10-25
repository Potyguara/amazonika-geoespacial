"""Prancha e memorial profissionais. Cálculo métrico mantido em pyproj.GRS80."""
from __future__ import annotations

import io
import math
import textwrap
from datetime import datetime
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from pyproj import CRS, Transformer
from reportlab.lib import colors
from reportlab.lib.pagesizes import A0, A1, A2, A3, A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from app.services.plant_memorial import _logo_path, load_document_template
from app.services.plant_memorial_v2 import (
    DISCLAIMER, Parcel, _dms, _raster_reader, build_joint_memorial,
)

FORMATS = {"A4": landscape(A4), "A3": landscape(A3),
           "A2": landscape(A2), "A1": landscape(A1), "A0": landscape(A0)}
SCALES = (100, 200, 250, 500, 750, 1000, 1500, 2000, 2500, 5000,
          7500, 10000, 15000, 20000, 25000, 50000, 100000, 200000, 500000)
GREEN = colors.HexColor("#174B3A")
DARK = colors.HexColor("#18382F")
MUTED = colors.HexColor("#51685D")
PALE = colors.HexColor("#EDF4EF")
WHITE = colors.white


def _pt_per_meter(denom: int) -> float:
    return 72.0 / (0.0254 * denom)


def _layout(
    projected: list[list[tuple[float, float]]],
    paper: str | None,
    denominator: int | None,
) -> tuple[str, float, float, int, tuple[float, float, float, float], tuple[float, float, float, float]]:
    name = (paper or "A4").upper()
    if name not in FORMATS:
        raise ValueError("Formato inválido. Escolha A4, A3, A2, A1 ou A0.")
    w, h = FORMATS[name]
    # Alocação fixa: coluna técnica à direita, quadro inferior à esquerda.
    side_x = w * .735
    view = (44.0, 215.0, side_x - 73.0, h - 322.0)
    if view[2] <= 100 or view[3] <= 140:
        raise ValueError("O formato escolhido não comporta a prancha.")
    all_pts = [point for ring in projected for point in ring]
    x0, y0 = min(p[0] for p in all_pts), min(p[1] for p in all_pts)
    x1, y1 = max(p[0] for p in all_pts), max(p[1] for p in all_pts)
    ext = (x0, y0, x1, y1)
    required_x = max(0.5, x1 - x0) * 1.12
    required_y = max(0.5, y1 - y0) * 1.12
    def fits(scale: int) -> bool:
        factor = _pt_per_meter(scale)
        return required_x * factor <= view[2] and required_y * factor <= view[3]
    recommended = next((v for v in SCALES if fits(v)), None)
    if recommended is None:
        raise ValueError(f"A área não cabe no formato {name}; escolha papel maior.")
    scale = denominator if denominator is not None else recommended
    if not 50 <= scale <= 1000000:
        raise ValueError("Escala inválida. Use denominador entre 50 e 1.000.000.")
    if not fits(scale):
        raise ValueError(
            f"Escala 1:{scale:,} não cabe no papel {name}. "
            f"Escolha 1:{recommended:,} ou uma escala mais reduzida, ou aumente o papel."
        )
    return name, w, h, scale, ext, view


def _label(pdf, lines: list[str], x: float, y: float,
           font_size: float = 8, accent=GREEN):
    longest = max(stringWidth(line, "Helvetica-Bold", font_size) for line in lines)
    width = longest + 14
    height = len(lines) * (font_size + 3) + 8
    pdf.saveState()
    pdf.setFillColor(WHITE)
    pdf.setStrokeColor(colors.HexColor("#B2C8BB"))
    pdf.setLineWidth(.6)
    pdf.roundRect(x-width/2, y-height/2, width, height, 5, fill=1, stroke=1)
    pdf.setFont("Helvetica-Bold", font_size)
    pdf.setFillColor(accent)
    for j, line in enumerate(lines):
        pdf.drawCentredString(x, y+height/2-8-(j*(font_size+3)), line)
    pdf.restoreState()
    return x-width/2, y-height/2, x+width/2, y+height/2


def _segment_labels(pdf, coords, segments, centroid, view_box):
    labels = []
    left, bottom, right, top = view_box
    for index, segment in enumerate(segments):
        x, y = coords[index]
        xx, yy = coords[(index+1) % len(coords)]
        midx, midy = (x+xx)/2, (y+yy)/2
        dx, dy = xx-x, yy-y
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy/length, dx/length
        # O rótulo fica no lado externo, ligado visualmente ao lado.
        if ((midx+nx*12-centroid[0])**2 + (midy+ny*12-centroid[1])**2 <
            (midx-centroid[0])**2 + (midy-centroid[1])**2):
            nx, ny = -nx, -ny
        azimuth = segment["azimuth"]
        degree = int(azimuth)
        minute = int((azimuth-degree)*60)
        second = int(round((((azimuth-degree)*60)-minute)*60))
        if second == 60: minute += 1; second = 0
        if minute == 60: degree += 1; minute = 0
        heading = f"Az {degree:03d}°{minute:02d}'{second:02d}\""
        distance = f"D {segment['distance']:.2f} m"
        width = max(stringWidth(heading, "Helvetica-Bold", 8),
                    stringWidth(distance, "Helvetica-Bold", 8)) + 16
        candidates = []
        for radius in (28, 48, 68, 90):
            for tangent in (0, -28, 28, -53, 53):
                tx, ty = dx/length, dy/length
                xx2 = max(left+width/2+3, min(right-width/2-3, midx+nx*radius+tx*tangent))
                yy2 = max(bottom+22, min(top-22, midy+ny*radius+ty*tangent))
                box = (xx2-width/2, yy2-16, xx2+width/2, yy2+16)
                hit = sum(
                    not (box[2] + 3 < placed[0] or box[0]-3 > placed[2] or
                         box[3]+3 < placed[1] or box[1]-3 > placed[3])
                    for placed in labels
                )
                candidates.append((hit, radius+abs(tangent)*.1, xx2, yy2))
        _, _, lx, ly = min(candidates)
        pdf.saveState()
        pdf.setStrokeColor(colors.HexColor("#71897D"))
        pdf.setLineWidth(.65)
        pdf.line(midx, midy, lx, ly)
        pdf.restoreState()
        labels.append(_label(pdf, [heading, distance], lx, ly))


def _short_table(pdf, parcels, projected, transformer, bounds, max_inline: int):
    total = sum(len(p.points) for p in parcels)
    left, bottom, right, top = bounds
    # O resumo integra a planta; volumes maiores recebem quadro adicional.
    if total > max_inline:
        pdf.setFont("Helvetica-Bold", 9)
        pdf.setFillColor(GREEN)
        pdf.drawString(left+8, top-23, "QUADRO DE COORDENADAS")
        pdf.setFont("Helvetica", 8)
        pdf.drawString(left+8, top-42, f"{total} vértices — quadro completo na folha seguinte")
        return
    cols = [left+8, left+150, left+265, left+380, left+500, left+607]
    pdf.saveState()
    pdf.setFillColor(GREEN)
    pdf.roundRect(left, top-31, right-left, 29, 5, fill=1, stroke=0)
    pdf.setFillColor(WHITE)
    pdf.setFont("Helvetica-Bold", 8.2)
    for x, header in zip(cols, ["VÉRTICE", "ESTE (m)", "NORTE (m)", "AZIMUTE", "DISTÂNCIA", "LOTE"]):
        if x < right-30: pdf.drawString(x, top-21, header)
    ypos = top-45
    pdf.setFont("Helvetica", 8)
    for p in parcels:
        for i, ((lon, lat), segment) in enumerate(zip(p.points, p.segments)):
            e, n = transformer.transform(lon, lat)
            row = (p.names[i][:22], f"{e:,.3f}", f"{n:,.3f}",
                   f"{segment['azimuth']:.2f}°", f"{segment['distance']:.2f} m", p.name[:12])
            if ypos < bottom+8: break
            if (int((top-ypos)/16) % 2) == 1:
                pdf.setFillColor(PALE); pdf.rect(left, ypos-4, right-left, 16, fill=1, stroke=0)
            pdf.setFillColor(DARK)
            for x, val in zip(cols, row):
                if x < right-30: pdf.drawString(x, ypos, val)
            ypos -= 17
    pdf.restoreState()


def _full_coordinate_sheet(pdf, parcels, transformer, zone, hemisphere, property_name, stamp):
    rows = [(p.name, p.names[i], _dms(lat, "lat"), _dms(lon, "lon"),
             *transformer.transform(lon, lat), s["azimuth"], s["distance"])
            for p in parcels for i, ((lon,lat),s) in enumerate(zip(p.points,p.segments))]
    if len(rows) <= 5:
        return
    pdf.showPage()
    w, h = landscape(A3)
    pdf.setPageSize((w,h))
    left, right = 42, w-42
    pdf.setFillColor(GREEN); pdf.rect(0,h-76,w,76,fill=1,stroke=0)
    pdf.setFillColor(WHITE); pdf.setFont("Helvetica-Bold",16)
    pdf.drawString(left,h-39,"QUADRO DE COORDENADAS E SEGMENTOS")
    pdf.setFont("Helvetica",10)
    pdf.drawString(left,h-58,f"{property_name[:68]}  |  SIRGAS 2000 / UTM {zone}{hemisphere}")
    cols = (left+10, left+165, left+285, left+415, left+550, left+670, left+790, left+915)
    y = h-105
    def header(y):
        pdf.setFillColor(PALE);pdf.rect(left,y-10,right-left,27,fill=1,stroke=0)
        pdf.setFillColor(GREEN);pdf.setFont("Helvetica-Bold",8.5)
        for x,t in zip(cols,("ÁREA","VÉRTICE","LATITUDE","LONGITUDE","ESTE","NORTE","AZIMUTE","DIST.")):
            pdf.drawString(x,y,t)
    header(y);y-=27
    for row in rows:
        if y < 60:
            pdf.setFont("Helvetica",7);pdf.setFillColor(MUTED);pdf.drawRightString(right,35,stamp)
            pdf.showPage();pdf.setPageSize((w,h));y=h-75;header(y);y-=27
        pdf.setFont("Helvetica",8);pdf.setFillColor(DARK)
        values=(str(row[0])[:21],str(row[1])[:18],str(row[2]),str(row[3]),
                f"{row[4]:,.3f}",f"{row[5]:,.3f}",f"{row[6]:.3f}°",f"{row[7]:.2f} m")
        for x,val in zip(cols,values):pdf.drawString(x,y,val)
        pdf.setStrokeColor(colors.HexColor("#E0E9E3"));pdf.line(left,y-5,right,y-5)
        y-=19
    pdf.setFont("Helvetica",7);pdf.setFillColor(MUTED);pdf.drawRightString(right,35,stamp)


def _memorial(pdf, parcels, title, owner, owner_rg, owner_cpf, address,
              responsible, professional, heading, croqui, stamp, config):
    w,h=A4;pdf.showPage();pdf.setPageSize(A4)
    margin=43
    y=h-96
    page=1
    style=ParagraphStyle("memorial_body",fontName="Helvetica",fontSize=9.6,
                         leading=15, textColor=DARK, spaceAfter=0)
    def new_page():
        nonlocal y,page
        pdf.setFont("Helvetica",7);pdf.setFillColor(MUTED)
        pdf.drawString(margin,28,str(config.get("document_footer") or "Amazônika Geoespacial")[:95])
        pdf.drawRightString(w-margin,28,f"{stamp}  |  Memorial {page}")
        pdf.showPage();pdf.setPageSize(A4);page+=1
        head();y=h-96
    def head():
        pdf.setFillColor(GREEN);pdf.rect(0,h-67,w,67,fill=1,stroke=0)
        pdf.setFillColor(WHITE);pdf.setFont("Helvetica-Bold",17)
        pdf.drawString(margin,h-36,heading[:51].upper())
        pdf.setFont("Helvetica",9)
        pdf.drawString(margin,h-52,title[:90])
        pdf.setStrokeColor(colors.HexColor("#CBDDD1"));pdf.line(margin,46,w-margin,46)
    head()
    def paragraph(value, bold=False, before=0, after=4):
        nonlocal y
        text=escape(value or "")
        if not text: return
        if bold:text=f"<b>{text}</b>"
        p=Paragraph(text,style)
        _,hh=p.wrap(w-2*margin,1000)
        if y-before-hh-after<59:new_page()
        y-=before
        p.drawOn(pdf,margin,y-hh)
        y-=hh+after
    # Identificação compacta em vez de 8 parágrafos separados.
    pdf.setFillColor(PALE);pdf.roundRect(margin,y-109,w-2*margin,105,8,fill=1,stroke=0)
    y-=16
    paragraph(f"IMÓVEL: {title}",bold=True,after=1)
    paragraph(f"DETENTOR/POSSEIRO: {owner or 'Não informado'}",after=1)
    if owner_rg or owner_cpf:paragraph(f"RG: {owner_rg or 'Não informado'}    |    CPF: {owner_cpf or 'Não informado'}",after=1)
    if address:paragraph(f"LOCALIZAÇÃO: {address}",after=1)
    y-=17
    pdf.setFillColor(GREEN)
    pdf.roundRect(margin,y-57,w-2*margin,55,8,fill=1,stroke=0)
    pdf.setFont("Helvetica-Bold",10);pdf.setFillColor(WHITE)
    pdf.drawString(margin+12,y-20,f"ÁREA TOTAL: {sum(p.area_ha for p in parcels):,.4f} ha")
    pdf.drawString(margin+12,y-39,f"PERÍMETRO: {sum(p.perimeter for p in parcels):,.3f} m")
    pdf.drawRightString(w-margin-12,y-39,f"POLÍGONOS: {len(parcels)}")
    y-=74
    # Texto contínuo, por confronto, com parágrafos justificados e sem linhas vazias.
    narrative=build_joint_memorial(
        parcels,title=title,owner=owner,responsible=responsible,croqui=croqui,
        owner_rg=owner_rg,owner_cpf=owner_cpf,property_address=address,
        memorial_heading=heading,professional=professional,
    )
    start=narrative.find("DESCRIÇÃO DO PERÍMETRO")
    end=narrative.find("________________________________________")
    if start<0:start=0
    if end<0:end=len(narrative)
    lines=narrative[start:end].splitlines()
    paragraphs=[]
    for line in lines:
        line=line.strip()
        if not line:continue
        paragraphs.append(line)
    for line in paragraphs:
        if line.startswith("DESCRIÇÃO DO PERÍMETRO"):
            paragraph(line,bold=True,before=9,after=7)
        elif line.startswith("OBSERVAÇÃO:"):
            paragraph(line,bold=True,before=10,after=4)
        elif line.startswith("Área:"):
            paragraph(line,bold=True,after=5)
        else:
            paragraph(line,after=3)
    if y<175:new_page()
    y-=12
    pdf.setStrokeColor(GREEN);pdf.line(margin+105,y,w-margin-105,y)
    y-=20
    pdf.setFillColor(DARK);pdf.setFont("Helvetica-Bold",10)
    pdf.drawCentredString(w/2,y,responsible or professional.get("full_name") or "Responsável técnico")
    y-=14
    prof_line=" - ".join(str(professional.get(field) or "").strip()
        for field in ("profession","specialization") if professional.get(field))
    pdf.setFont("Helvetica",8.5);pdf.drawCentredString(w/2,y,prof_line[:105])
    y-=13
    crea=" | ".join(str(professional.get(field) or "").strip()
        for field in ("crea","visto","incra_code") if professional.get(field))
    pdf.drawCentredString(w/2,y,crea[:105])
    y-=13
    if professional.get("art"):
        pdf.drawCentredString(w/2,y,f"ART informada: {professional['art']}"[:100])
    pdf.setFont("Helvetica",7);pdf.setFillColor(MUTED)
    pdf.drawString(margin,28,str(config.get("document_footer") or "Amazônika Geoespacial")[:95])
    pdf.drawRightString(w-margin,28,f"{stamp}  |  Memorial {page}")


def make_joint_pdf(*, parcels: list[Parcel], title: str,
                   owner_name: str | None, responsible_name: str | None, croqui: bool,
                   raster_b64: str | None, raster_source: str | None,
                   owner_rg: str | None=None, owner_cpf: str | None=None,
                   property_address: str | None=None,
                   plant_heading: str="PLANTA GEORREFERENCIADA",
                   memorial_heading: str="MEMORIAL DESCRITIVO",
                   professional: dict | None=None, qr_url: str | None=None,
                   paper_format: str | None="A3",
                   scale_denominator: int | None=None) -> tuple[bytes,str,int]:
    if not raster_b64:
        raise ValueError("É obrigatória a captura raster da planta de situação.")
    config=load_document_template()
    professional=professional or {}
    now=datetime.now(ZoneInfo("America/Belem"))
    stamp=now.strftime("%d/%m/%Y %H:%M:%S - Belém")
    allpts=[pt for parcel in parcels for pt in parcel.points]
    lon=sum(p[0] for p in allpts)/len(allpts)
    lat=sum(p[1] for p in allpts)/len(allpts)
    zone=max(1,min(60,int((lon+180)//6)+1))
    hemisphere="S" if lat<0 else "N"
    crs=CRS.from_proj4(f"+proj=utm +zone={zone} {'+south' if hemisphere=='S' else ''} +ellps=GRS80 +units=m +no_defs")
    transformer=Transformer.from_crs("EPSG:4674",crs,always_xy=True)
    projected=[[transformer.transform(*pt) for pt in p.points] for p in parcels]
    name,w,h,scale,ext,(vx,vy,vw,vh)=_layout(projected,paper_format,scale_denominator)
    x0,y0,x1,y1=ext
    factor=_pt_per_meter(scale)
    px=vx+(vw-(x1-x0)*factor)/2
    py=vy+(vh-(y1-y0)*factor)/2
    def xy(x,y):return (px+(x-x0)*factor,py+(y-y0)*factor)
    map_box=(vx,vy,vx+vw,vy+vh)
    side=w*.735
    image=_raster_reader(raster_b64)
    buffer=io.BytesIO()
    pdf=canvas.Canvas(buffer,pagesize=(w,h),pageCompression=1)
    pdf.setTitle(f"{title} | Planta e memorial descritivo")

    # Moldura de impressão e cabeçalho sem faixa em branco superior.
    pdf.setFillColor(WHITE);pdf.rect(0,0,w,h,fill=1,stroke=0)
    pdf.setStrokeColor(colors.HexColor("#738F7D"));pdf.setLineWidth(.8)
    pdf.rect(24,24,w-48,h-48,fill=0,stroke=1)
    pdf.setFillColor(GREEN);pdf.rect(24,h-92,side-24,68,fill=1,stroke=0)
    pdf.setFillColor(WHITE);pdf.setFont("Helvetica-Bold",15)
    pdf.drawString(39,h-54,plant_heading[:70].upper())
    pdf.setFont("Helvetica",10);pdf.drawString(39,h-72,title[:90])
    pdf.setStrokeColor(colors.HexColor("#C2D4C9"));pdf.rect(vx-13,vy-10,vw+26,vh+20,fill=0,stroke=1)

    # Grade UTM espaçada conforme escala, discreta e limitada à moldura cartográfica.
    span=max(x1-x0,y1-y0,1)
    gridstep=10**math.floor(math.log10(max(1,span/5)))
    if span/gridstep>8:gridstep*=2
    if span/gridstep<3:gridstep/=2
    pdf.saveState()
    pdf.setStrokeColor(colors.HexColor("#DEE8E1"));pdf.setLineWidth(.5)
    pdf.setFont("Helvetica",7);pdf.setFillColor(MUTED)
    for k in range(150):
        east=(math.floor(x0/gridstep)+k)*gridstep
        if east>x1+gridstep:break
        ex=xy(east,y0)[0]
        if vx<=ex<=vx+vw:
            pdf.line(ex,vy,ex,vy+vh)
            pdf.drawCentredString(ex,vy-7,f"{east:,.0f}")
    for k in range(150):
        north=(math.floor(y0/gridstep)+k)*gridstep
        if north>y1+gridstep:break
        ny=xy(x0,north)[1]
        if vy<=ny<=vy+vh:
            pdf.line(vx,ny,vx+vw,ny)
            pdf.drawRightString(vx-17,ny-3,f"{north:,.0f}")
    pdf.restoreState()
    pdf.setFont("Helvetica-Bold",8);pdf.setFillColor(MUTED)
    pdf.drawString(vx,vy+vh+14,f"UTM {zone}{hemisphere} • SIRGAS 2000")
    # Traçado e etiquetas independentes da opacidade do polígono.
    parcel_colors=(colors.HexColor("#176847"),colors.HexColor("#255E9A"),
                   colors.HexColor("#B47136"),colors.HexColor("#7A4C91"))
    for j,(parcel,ring) in enumerate(zip(parcels,projected)):
        points=[xy(*pt) for pt in ring]
        path=pdf.beginPath();path.moveTo(*points[0])
        for pt in points[1:]:path.lineTo(*pt)
        path.close()
        pdf.saveState()
        pdf.setFillColor(colors.HexColor("#E8F4E9"))
        pdf.setStrokeColor(parcel_colors[j%len(parcel_colors)])
        pdf.setLineWidth(2.0)
        pdf.drawPath(path,fill=1,stroke=1)
        pdf.restoreState()
        cx=sum(x for x,_ in points)/len(points);cy=sum(y for _,y in points)/len(points)
        _segment_labels(pdf,points,parcel.segments,(cx,cy),map_box)
        for i,(x,y) in enumerate(points):
            pdf.saveState()
            pdf.setFillColor(WHITE);pdf.setStrokeColor(GREEN);pdf.circle(x,y,3.4,fill=1,stroke=1)
            pdf.restoreState()
            # Nome escuro com pequeno fundo branco, mesmo com linhas de grade atrás.
            text=parcel.names[i][:26]
            tw=stringWidth(text,"Helvetica-Bold",8)
            tx=max(vx+5,min(vx+vw-tw-6,x+7))
            ty=max(vy+6,min(vy+vh-10,y+9))
            pdf.setFillColor(WHITE);pdf.rect(tx-2,ty-2,tw+5,12,fill=1,stroke=0)
            pdf.setFont("Helvetica-Bold",8);pdf.setFillColor(DARK);pdf.drawString(tx,ty,text)

    # Quadro de coordenadas integrado à prancha para lotes de pequena dimensão.
    _short_table(pdf,parcels,projected,transformer,(35,70,side-19,193),5)
    # Norte, escala gráfica e escala nominal têm papéis diferentes.
    nx,ny=vx+20,vy+vh-22
    pdf.setStrokeColor(GREEN);pdf.setLineWidth(2)
    pdf.line(nx,ny-30,nx,ny);pdf.line(nx,ny,nx-6,ny-10);pdf.line(nx,ny,nx+6,ny-10)
    pdf.setFont("Helvetica-Bold",12);pdf.setFillColor(GREEN);pdf.drawCentredString(nx,ny+7,"N")
    pdf.setFont("Helvetica-Bold",8.5)
    pdf.drawString(vx,202,f"ESCALA NOMINAL  1:{scale:,}   |   FORMATO {name}   |   IMPRIMIR EM 100%")
    # Coluna de identificação: títulos legíveis, não cinza com opacidade.
    right_x=side+12;right_w=w-right_x-37
    pdf.setFillColor(PALE);pdf.rect(side,24,w-side-24,h-48,fill=1,stroke=0)
    pdf.setFillColor(GREEN);pdf.rect(side,h-92,w-side-24,68,fill=1,stroke=0)
    pdf.setFillColor(WHITE);pdf.setFont("Helvetica-Bold",11)
    pdf.drawString(right_x,h-52,"QUADRO TÉCNICO")
    pdf.setFont("Helvetica",8)
    pdf.drawString(right_x,h-70,"PLANTA + MEMORIAL  |  " + name)
    logo=_logo_path(config)
    if logo:
        try:pdf.drawImage(ImageReader(str(logo)),right_x,h-154,width=right_w*.46,height=49,
                         preserveAspectRatio=True,mask="auto")
        except (ValueError,OSError):pass
    y=h-166
    def field(label,value):
        nonlocal y
        pdf.setFont("Helvetica-Bold",7);pdf.setFillColor(MUTED);pdf.drawString(right_x,y,label.upper());y-=12
        p=Paragraph(escape(str(value or "Não informado")),
                    ParagraphStyle("mini",fontName="Helvetica",fontSize=8.6,leading=11,
                                   textColor=DARK))
        _,ph=p.wrap(right_w,100)
        p.drawOn(pdf,right_x,y-ph+2);y-=ph+11
    field("IMÓVEL",title)
    field("DETENTOR / POSSEIRO",owner_name)
    if name != "A4": field("LOCALIZAÇÃO",property_address)
    field("ÁREA TOTAL",f"{sum(p.area_ha for p in parcels):,.4f} ha")
    if name != "A4": field("PERÍMETRO",f"{sum(p.perimeter for p in parcels):,.3f} m")
    field("DATUM / FUSO",f"SIRGAS 2000 / UTM {zone}{hemisphere}")
    field("TÉCNICO",responsible_name or professional.get("full_name"))
    if name != "A4":
        field("REGISTRO", "  |  ".join(str(professional.get(k) or "")
              for k in ("crea","visto") if professional.get(k)))
    # Raster com espaço reservado e proporção mantida: impresso com fundo/opacidade integrais.
    image_bottom=142 if name == "A4" else 171
    image_height=min(137,max(90,y-image_bottom-29))
    if y<image_bottom+image_height+33:
        image_height=max(70,y-image_bottom-29)
    if image_height<60:raise ValueError("Quadro técnico sem espaço para imagem. Escolha formato maior.")
    pdf.setFont("Helvetica-Bold",8);pdf.setFillColor(GREEN)
    pdf.drawString(right_x,image_bottom+image_height+13,"PLANTA DE SITUAÇÃO • RASTER DO MAPA")
    pdf.setFillColor(WHITE);pdf.setStrokeColor(colors.HexColor("#CAD9CF"))
    pdf.rect(right_x-2,image_bottom-3,right_w+4,image_height+6,fill=1,stroke=1)
    pdf.drawImage(image,right_x,image_bottom,right_w,image_height,preserveAspectRatio=True,anchor="c")
    pdf.setFont("Helvetica",6.5);pdf.setFillColor(MUTED)
    pdf.drawString(right_x,image_bottom-14,(raster_source or "Raster de referência")[:55])
    # QR e assinatura.
    if qr_url:
        import qrcode
        png=io.BytesIO();qrcode.make(qr_url,box_size=4,border=1).save(png,format="PNG");png.seek(0)
        pdf.drawImage(ImageReader(png),right_x,50,78,78)
        pdf.setFont("Helvetica-Bold",7.2);pdf.setFillColor(GREEN)
        pdf.drawString(right_x+86,103,"ACESSO AO DOCUMENTO")
        pdf.setFont("Helvetica",7);pdf.drawString(right_x+86,90,"QR com login e autorização")
    pdf.setFont("Helvetica",7);pdf.setFillColor(DARK)
    pdf.drawString(right_x,37,stamp[:48])
    pdf.setFont("Helvetica",6.5)
    pdf.drawString(37,25,str(config.get("document_footer") or "Documento técnico gerado pelo Amazônika Geoespacial.")[:90])
    if croqui:
        pdf.saveState();pdf.setFillColor(colors.HexColor("#8D4F2E"))
        pdf.setFont("Helvetica-Bold",6.9)
        note=textwrap.wrap(DISCLAIMER,width=max(45,int((side-55)/4.5)))
        for i,line in enumerate(note[:3]):pdf.drawString(38,63-i*10,line)
        pdf.restoreState()

    _full_coordinate_sheet(pdf,parcels,transformer,zone,hemisphere,title,stamp)
    _memorial(pdf,parcels,title,owner_name,owner_rg,owner_cpf,property_address,
              responsible_name,professional,memorial_heading,croqui,stamp,config)
    pdf.save()
    return buffer.getvalue(),name,scale
