"""Memoriais A/B/C baseados nos três modelos profissionais fornecidos.

Renderização vetorial A4: identificação, confrontações, croqui e narrativa
geodésica agrupada. O fluxo de edição livre continua no renderer legado.
"""
from __future__ import annotations

import math
from datetime import date
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.pdfbase import pdfmetrics

from app.services.plant_memorial_v2 import _br_number, _dms, _azimuth_minutes, DISCLAIMER
from app.services.plant_detail_elements import group_confrontations

W,H=A4


def _style_for(template):
    choices={
      "classic_lateral":dict(primary="#154D3B",pale="#EFF5F1",gold="#BE923E",accent="#208363",dark="#1F3530"),
      "cartographic_frame":dict(primary="#202C3B",pale="#EDF4F4",gold="#D19B2E",accent="#0E9B88",dark="#202C3B"),
      "modern_lateral":dict(primary="#162E53",pale="#EBF0F8",gold="#BC7848",accent="#C17F48",dark="#1E3455"),
    }
    return choices[template]


def _col(pdf,value):
    return colors.HexColor(value)


def _str(pdf,text,x,y,size=8,font="Helvetica",color="#20352D",*,right=False,center=False):
    pdf.setFillColor(_col(color))
    pdf.setFont(font,size)
    if right:
        pdf.drawRightString(x,y,str(text))
    elif center:
        pdf.drawCentredString(x,y,str(text))
    else:
        pdf.drawString(x,y,str(text))


def _para(text,size=8,leading=11,color="#34483D",bold=False):
    style=ParagraphStyle("memorial_tpl",fontName="Helvetica-Bold" if bold else "Helvetica",
                         fontSize=size,leading=leading,textColor=_col(color),
                         splitLongWords=0)
    return Paragraph(text,style)


def _fit_para(pdf,text,x,top,width,*,size=7.2,leading=10,color="#273A30",bold=False):
    item=_para(escape(str(text)),size=size,leading=leading,color=color,bold=bold)
    _,height=item.wrap(width,1000)
    item.drawOn(pdf,x,top-height)
    return height


def _panel(pdf,x,y,w,h,title,c):
    pdf.setFillColor(colors.white)
    pdf.setStrokeColor(_col("#D2DBD7"))
    pdf.roundRect(x,y,w,h,4,fill=1,stroke=1)
    pdf.setFillColor(_col(c["primary"]))
    pdf.roundRect(x,y+h-23,w,23,4,stroke=0,fill=1)
    pdf.rect(x,y+h-23,w,11,stroke=0,fill=1)
    pdf.setFillColor(_col(c["gold"]))
    pdf.rect(x,y+h-23,3,23,stroke=0,fill=1)
    _str(pdf,title,x+9,y+h-15,6.8,"Helvetica-Bold", "#FFFFFF")


def _short(name):
    import re
    return re.sub(r"^.*?-(?=[MV]-)", "",str(name))


def _sketch(pdf,parcel,x,y,w,h,c):
    """Croqui topológico vetorial; não representa mapa em escala fixa."""
    if not parcel:
        return
    points=parcel.points
    xs=[p[0] for p in points]
    ys=[p[1] for p in points]
    dx=max(max(xs)-min(xs),1e-9)
    dy=max(max(ys)-min(ys),1e-9)
    scale=min((w-34)/dx,(h-40)/dy)
    def project(point):
        return (x+(w-dx*scale)/2+(point[0]-min(xs))*scale,
                y+19+(h-35-dy*scale)/2+(point[1]-min(ys))*scale)
    coords=[project(p) for p in points]
    path=pdf.beginPath()
    path.moveTo(*coords[0])
    for point in coords[1:]:
        path.lineTo(*point)
    path.close()
    pdf.setFillColor(_col("#D4E8DA" if c["primary"]=="#154D3B" else "#D0DCEC"))
    pdf.setStrokeColor(_col(c["primary"]))
    pdf.setLineWidth(1)
    pdf.drawPath(path,stroke=1,fill=1)
    for i,name in enumerate(parcel.names):
        if "-M-" not in name.upper() and not name.upper().startswith("M-"):
            continue
        px,py=coords[i]
        pdf.setFillColor(_col(c["gold"]))
        pdf.circle(px,py,2.8,stroke=0,fill=1)
        _str(pdf,_short(name),px+4,py+4,5.0,"Helvetica-Bold",c["primary"])
    _str(pdf,"N",x+12,y+h-17,7,"Helvetica-Bold",c["primary"])
    pdf.setStrokeColor(_col(c["primary"]))
    pdf.line(x+14,y+h-36,x+14,y+h-21)
    pdf.line(x+14,y+h-21,x+11,y+h-27)
    pdf.line(x+14,y+h-21,x+17,y+h-27)
    _str(pdf,"Croqui esquemático · sem escala fixa",x+7,y+6,5.4,color="#60756A")


def _identity(pdf,y,title,owner,owner_rg,owner_cpf,address,parcels,
              metadata,zone,hemi,survey_date,c):
    height=165
    x=42
    width=W-84
    _panel(pdf,x,y-height,width,height,"IDENTIFICAÇÃO DO IMÓVEL",c)
    pdf.setFillColor(_col(c["pale"]))
    pdf.rect(x+1,y-65,width-2,42,stroke=0,fill=1)
    values=[
        ("ÁREA",f"{_br_number(sum(p.area_ha for p in parcels),4)} ha"),
        ("PERÍMETRO",f"{_br_number(sum(p.perimeter for p in parcels),2)} m"),
        ("PONTOS",str(sum(len(p.points) for p in parcels))),
    ]
    col=width/3
    for i,(label,value) in enumerate(values):
        _str(pdf,label,x+12+i*col,y-37,6.1,"Helvetica-Bold",c["gold"])
        _str(pdf,value,x+12+i*col,y-57,13,"Helvetica-Bold",c["primary"])
    metadata=metadata or {}
    attrs=[
        ("IMÓVEL",title),
        ("DETENTOR / POSSEIRO",owner or "Não informado"),
        ("CPF / RG",f"{owner_cpf or '—'} · RG: {owner_rg or '—'}"),
        ("LOCALIZAÇÃO",address or "Não informada"),
        ("SITUAÇÃO JURÍDICA",metadata.get("legal_status") or "Não informada"),
        ("NATUREZA DA ÁREA",metadata.get("area_nature") or "Não informada"),
        ("DATUM / PROJEÇÃO",f"SIRGAS 2000 · UTM {zone}{hemi}"),
        ("DATA DE ELABORAÇÃO",survey_date.strftime("%d/%m/%Y")),
    ]
    for i,(label,value) in enumerate(attrs):
        colidx=i%2
        row=i//2
        xx=x+12+colidx*(width/2)
        yy=y-77-row*21
        _str(pdf,label,xx,yy,5.45,"Helvetica-Bold",c["gold"])
        _fit_para(pdf,value,xx,yy-2,width/2-24,size=6.8,leading=8.1,
                  color=c["dark"],bold=True)
    return y-height


def _confrontation_and_sketch(pdf,y,parcels,c):
    groups=group_confrontations(parcels)
    x=42
    gap=10
    lw=298
    rw=W-84-lw-gap
    height=205
    lefty=y-height
    _panel(pdf,x,lefty,lw,height,"CONFRONTAÇÕES",c)
    _panel(pdf,x+lw+gap,lefty,rw,height,"CROQUI ESQUEMÁTICO",c)
    line_top=y-32
    pdf.setFillColor(_col(c["pale"]))
    pdf.rect(x+7,line_top-17,lw-14,17,stroke=0,fill=1)
    _str(pdf,"CONFRONTANTE",x+11,line_top-11,5.7,"Helvetica-Bold",c["primary"])
    _str(pdf,"TRECHO",x+170,line_top-11,5.7,"Helvetica-Bold",c["primary"])
    _str(pdf,"EXT. (m)",x+lw-10,line_top-11,5.7,"Helvetica-Bold",c["primary"],right=True)
    yy=line_top-20
    for group in groups[:6]:
        name=group["name"]
        segment=f"{_short(group['start'])} – {_short(group['end'])}"
        name_h=_fit_para(pdf,name,x+11,yy,148,size=6.5,leading=8.3,
                         color=c["dark"],bold=True)
        segment_h=_fit_para(pdf,segment,x+170,yy,66,size=6.2,leading=8.0)
        row_h=max(18,name_h+5,segment_h+5)
        _str(pdf,_br_number(group["distance"],2),x+lw-10,yy-8,6.3,
             "Helvetica-Bold",c["primary"],right=True)
        yy-=row_h
        pdf.setStrokeColor(_col("#E2E9E5"))
        pdf.line(x+10,yy+2,x+lw-9,yy+2)
    footer=lefty+14
    if yy<footer+14 and len(groups)>6:
        _str(pdf,"Confrontações adicionais na descrição",x+10,footer+16,
             5.9,color="#78521D")
    _str(pdf,"PERÍMETRO TOTAL",x+10,footer,6.1,"Helvetica-Bold",c["gold"])
    _str(pdf,f"{_br_number(sum(p.perimeter for p in parcels),2)} m",
         x+lw-11,footer-1,8.3,"Helvetica-Bold",c["primary"],right=True)
    _sketch(pdf,parcels[0] if parcels else None,x+lw+gap+7,lefty+8,rw-14,height-35,c)
    return lefty


def render_memorial_professional(pdf,*,parcels,template,title,owner,owner_rg,
                                 owner_cpf,address,professional,property_metadata,
                                 survey_date,stamp,croqui,edited_memorial=None):
    c=_style_for(template)
    pts=[xy for p in parcels for xy in p.points]
    lon=sum(x for x,y in pts)/len(pts)
    lat=sum(y for x,y in pts)/len(pts)
    zone=max(1,min(60,int((lon+180)//6)+1))
    hemi="S" if lat<0 else "N"
    page=0
    margin=42

    def header(first):
        pdf.setPageSize(A4)
        if template=="cartographic_frame":
            pdf.setFillColor(_col(c["accent"]))
            pdf.rect(0,0,16,H,stroke=0,fill=1)
        if template=="modern_lateral":
            pdf.setFillColor(_col(c["primary"]))
            pdf.rect(20,H-112,W-40,91,stroke=0,fill=1)
            _str(pdf,"MEMORIAL DESCRITIVO",W/2,H-54,11,"Helvetica-Bold",
                 "#FFFFFF",center=True)
            _str(pdf,title.upper(),W/2,H-89,17,"Helvetica-Bold",
                 "#FFFFFF",center=True)
        elif first:
            pdf.setFillColor(_col(c["primary"]))
            pdf.rect(28,H-110,W-56,77,fill=1,stroke=0)
            pdf.setFillColor(_col(c["gold"]))
            pdf.rect(28,H-113,W-56,3,fill=1,stroke=0)
            _str(pdf,"MEMORIAL DESCRITIVO",47,H-56,8,"Helvetica-Bold","#FFFFFF")
            _str(pdf,title.upper(),47,H-88,18,"Helvetica-Bold","#FFFFFF")
        else:
            pdf.setFillColor(_col(c["primary"]))
            pdf.rect(28,H-70,W-56,37,stroke=0,fill=1)
            _str(pdf,f"MEMORIAL DESCRITIVO  ·  {title.upper()}",W/2,
                 H-55,9,"Helvetica-Bold","#FFFFFF",center=True)
        if first and template=="cartographic_frame":
            pdf.setStrokeColor(_col(c["primary"]))
            pdf.rect(23,23,W-46,H-46,stroke=1,fill=0)

    def footer():
        pdf.setStrokeColor(_col("#CFDAD3"))
        pdf.line(margin,46,W-margin,46)
        if croqui:
            caveat=_para(escape(DISCLAIMER),size=5.7,leading=6.8,color="#96453A")
            _,ph=caveat.wrap(W-2*margin-40,40)
            caveat.drawOn(pdf,margin,37-ph)
        _str(pdf,f"Fl. {page}",W-margin,27,6.2,"Helvetica-Bold",c["primary"],right=True)
        _str(pdf,f"Gerado em {stamp}",margin,17,5.7,color="#73857B")
        _str(pdf,f"SIRGAS 2000 · UTM {zone}{hemi}",W-margin,17,5.7,
             color="#73857B",right=True)

    def new_page(first=False):
        nonlocal page,y
        if page:
            footer()
            pdf.showPage()
        page+=1
        header(first)
        y=H-(125 if first else 88)

    new_page(True)
    y=_identity(pdf,y,title,owner,owner_rg,owner_cpf,address,parcels,
                property_metadata,zone,hemi,survey_date,c)-12
    y=_confrontation_and_sketch(pdf,y,parcels,c)-24
    if y<145:
        new_page()
    _str(pdf,"DESCRIÇÃO DO PERÍMETRO",margin,y,11,"Helvetica-Bold",c["primary"])
    pdf.setStrokeColor(_col(c["gold"]))
    pdf.setLineWidth(2)
    pdf.line(margin,y-6,margin+75,y-6)
    y-=24

    def narrative(html,*,keep_min=18,space=7):
        nonlocal y
        pending=_para(html,size=8.1,leading=11.7,color=c["dark"])
        while True:
            remaining=y-68
            if remaining<max(keep_min,22):
                new_page()
                remaining=y-68
            blocks=pending.split(W-2*margin,remaining)
            if not blocks:
                new_page()
                continue
            first=blocks[0]
            _,ph=first.wrap(W-2*margin,remaining)
            first.drawOn(pdf,margin,y-ph)
            y-=ph
            if len(blocks)==1:
                y-=space
                return
            new_page()
            pending=blocks[1]

    for p_index,parcel in enumerate(parcels):
        if p_index:
            if y<120:new_page()
            _str(pdf,f"POLÍGONO {p_index+1}",margin,y,8,"Helvetica-Bold",c["primary"])
            y-=21
        starting=parcel.segments[0]
        alt=parcel.altitudes[0]
        altpart=f" e Altitude: {_br_number(alt,2)} m" if alt is not None else ""
        intro=(f"Inicia-se a descrição deste perímetro no vértice <b>{escape(starting['start'])}</b>, "
               f"de coordenadas (Longitude: {_dms(starting['lon'],'lon')}, "
               f"Latitude: {_dms(starting['lat'],'lat')}{altpart}); linha ideal.")
        narrative(intro,space=13)
        groups=group_confrontations([parcel])
        for idx,group in enumerate(groups):
            if y<160:new_page()
            bar_h=23
            pdf.setFillColor(_col(c["primary"]))
            pdf.roundRect(margin,y-bar_h,W-2*margin,bar_h,3,stroke=0,fill=1)
            pdf.setFillColor(_col(c["gold"]))
            pdf.rect(margin,y-bar_h,4,bar_h,fill=1,stroke=0)
            _str(pdf,str(idx+1),margin+15,y-15,8,"Helvetica-Bold","#FFFFFF")
            group_title=f"Confrontante: {group['name']}"
            _str(pdf,group_title[:64],margin+32,y-15,7.2,"Helvetica-Bold","#FFFFFF")
            _str(pdf,f"{_short(group['start'])} → {_short(group['end'])} · "
                 f"{_br_number(group['distance'],2)} m",
                 W-margin-8,y-15,6.6,"Helvetica-Bold","#FFFFFF",right=True)
            y-=32
            prose=(f"Deste, segue confrontando com <b>{escape(group['name'])}</b>, "
                   "com os seguintes azimutes e distâncias: ")
            for segindex in group["segments"]:
                seg=parcel.segments[segindex]
                end_idx=(segindex+1)%len(parcel.points)
                alt=parcel.altitudes[end_idx]
                altpart=f" e Altitude: {_br_number(alt,2)} m" if alt is not None else ""
                close=end_idx==0
                ending=("ponto inicial da descrição deste perímetro."
                        if close else
                        f"(Longitude: {_dms(seg['next_lon'],'lon')}, "
                        f"Latitude: {_dms(seg['next_lat'],'lat')}{altpart})")
                prose+=(f"<b>{_azimuth_minutes(seg['azimuth'])} e "
                        f"{_br_number(seg['distance'],2)} m</b> até o vértice "
                        f"<b>{escape(seg['end'])}</b>, {ending}; ")
            narrative(prose.rstrip("; ")+".",space=12)
        narrative(f"<b>ÁREA DESTA PARCELA:</b> {_br_number(parcel.area_ha,4)} ha · "
                  f"<b>PERÍMETRO:</b> {_br_number(parcel.perimeter,2)} m",space=10)
    narrative("Coordenadas referenciadas ao SIRGAS 2000; azimutes e distâncias "
              "geodésicos calculados sobre o elipsóide GRS80. A precisão depende "
              "da fonte da geometria; esta emissão não constitui certificação fundiária.",
              space=13)
    if y<225:
        new_page()
    _str(pdf,f"{address or 'Local não informado'}, "
         f"{survey_date.strftime('%d/%m/%Y')}.",margin,y,7.2,color=c["dark"])
    y-=18
    width=(W-2*margin-20)/3
    names=[
        ("PROPRIETÁRIO / DETENTOR",owner or "Não informado",
         f"CPF: {owner_cpf or '—'}"),
        ("RESPONSÁVEL TÉCNICO",professional.get("full_name") or "Não informado",
         " · ".join(
             f"{label}: {professional[key]}" for key,label in (
                 ("profession","Profissão"),("specialization","Especialização"),
                 ("crea","CREA/CAU"),("visto","Visto"),("incra_code","INCRA"),
                 ("art","ART"),
             ) if professional.get(key)
         ) or "Registro/ART não informado"),
        ("CARIMBO DO RESPONSÁVEL TÉCNICO","",""),
    ]
    for i,(label,name,doc) in enumerate(names):
        xx=margin+i*(width+10)
        _str(pdf,label,xx,y,5.6,"Helvetica-Bold",c["gold"])
        pdf.setStrokeColor(_col(c["primary"]))
        pdf.line(xx,y-43,xx+width,y-43)
        _fit_para(pdf,name,xx,y-49,width,size=6.5,leading=8,
                  color=c["dark"],bold=True)
        _fit_para(pdf,doc,xx,y-69,width,size=5.8,leading=7.1,color="#69796E")
    footer()
