"""Elementos técnicos da prancha: apresentação independente dos dados geodésicos.

Confrontações: agregação de trechos contíguos em ordem perimetral, inclusive
a junção do último com o primeiro segmento. A soma é calculada dos segmentos
de origem, não de um campo de apresentação.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Paragraph

from app.services.plant_memorial_v2 import _br_number


def group_confrontations(parcels):
    groups = []
    for parcel in parcels:
        labels = [str(v or "Não informado").strip() for v in parcel.confrontants]
        if len(labels) != len(parcel.segments):
            raise ValueError("Quantidade de confrontantes incompatível com os segmentos.")
        local = []
        for i, (label, segment) in enumerate(zip(labels, parcel.segments)):
            distance = float(segment["distance"])
            if not math.isfinite(distance) or distance < 0:
                raise ValueError("Distância perimetral inválida.")
            if local and local[-1]["name"].casefold() == label.casefold():
                local[-1]["end"] = segment["end"]
                local[-1]["distance"] += distance
                local[-1]["segments"].append(i)
            else:
                local.append(dict(name=label,start=segment["start"],end=segment["end"],
                                  distance=distance,segments=[i]))
        # Preservar a sequência da planilha: o confrontante do primeiro
        # e do último trecho pode ser o mesmo, mas ambos são trechos
        # distintos no quadro de confrontações.
        groups.extend(local)
    return groups


def grouped_label_positions(parcel):
    """Um rótulo central para cada sequência contígua na ordem original."""
    labels=[str(v or "").strip() for v in parcel.confrontants]
    positions=set()
    i=0
    while i<len(labels):
        j=i+1
        while j<len(labels) and labels[j].casefold()==labels[i].casefold():
            j+=1
        if labels[i]:
            positions.add(i+(j-i)//2)
        i=j
    return positions


def _font_names():
    from app.services.plant_template_engine import _fonts
    return _fonts()


def _box(pdf, rect, heading, palette):
    dark, pale, accent, paper = palette
    pdf.setFillColor(colors.HexColor("#FFFFFF"))
    pdf.setStrokeColor(colors.HexColor("#CBD7D1"))
    pdf.roundRect(rect.x,rect.y,rect.w,rect.h,5,stroke=1,fill=1)
    pdf.setFillColor(colors.HexColor(dark))
    pdf.roundRect(rect.x,rect.top-25,rect.w,25,5,stroke=0,fill=1)
    pdf.rect(rect.x,rect.top-25,rect.w,11,fill=1,stroke=0)
    pdf.setFillColor(colors.HexColor(accent))
    pdf.rect(rect.x,rect.top-25,4,25,stroke=0,fill=1)
    _,bold,_ = _font_names()
    pdf.setFont(bold,8)
    pdf.setFillColor(colors.white)
    pdf.drawString(rect.x+12,rect.top-17,heading)


def _text(pdf,value,x,baseline,*,size=7,bold=False,color="#20352D",max_width=None):
    regular,strong,_ = _font_names()
    font = strong if bold else regular
    value = str(value if value is not None else "Não informado")
    if max_width and pdfmetrics.stringWidth(value,font,size)>max_width:
        style=ParagraphStyle("details",fontName=font,fontSize=size,leading=size+2,
                             textColor=colors.HexColor(color))
        item=Paragraph(escape(value),style)
        _,height=item.wrap(max_width,300)
        item.drawOn(pdf,x,baseline-height+size)
        return height
    pdf.setFont(font,size)
    pdf.setFillColor(colors.HexColor(color))
    pdf.drawString(x,baseline,value)
    return size


def confrontations_card(pdf, rect, parcels, palette):
    groups = group_confrontations(parcels)
    _box(pdf,rect,"CONFRONTAÇÕES",palette)
    dark,pale,accent,_=palette
    x=rect.x+9
    top=rect.top-32
    available=rect.w-18
    ext_w=max(48,available*.19)
    stretch=available-ext_w
    name_w=stretch*.57
    segment_w=stretch-name_w
    pdf.setFillColor(colors.HexColor("#EFF5F1"))
    pdf.rect(x,top-22,available,22,stroke=0,fill=1)
    _text(pdf,"CONFRONTANTE",x+4,top-15,size=6.7,bold=True,color=dark)
    _text(pdf,"TRECHO",x+name_w+4,top-15,size=6.7,bold=True,color=dark)
    _text(pdf,"EXT. (m)",x+name_w+segment_w+3,top-15,size=6.7,bold=True,color=dark)
    row_top=top-22
    footer_y=rect.y+8
    available_h=row_top-(footer_y+29)
    if len(groups)>0 and available_h/max(len(groups),1)<15:
        # Nunca descartar confrontantes nem falsificar o perímetro; sinalizar
        # explicitamente excesso e remeter ao memorial completo.
        count=max(0,int(available_h//16)-1)
        shown=groups[:count]
        overflow=len(groups)-len(shown)
    else:
        shown=groups
        overflow=0
    row_h=min(28,max(15,available_h/max(1,len(shown))))
    for i,group in enumerate(shown):
        yy=row_top-(i+1)*row_h
        if yy<=footer_y+23:
            overflow=len(groups)-i
            break
        _text(pdf,group["name"],x+4,yy+7,size=7,bold=True,
              color="#243A30",max_width=name_w-8)
        _text(pdf,f'{group["start"]} – {group["end"]}',x+name_w+4,yy+7,
              size=6.6,color="#53685E",max_width=segment_w-8)
        text=_br_number(group["distance"],2)
        regular,bold,_=_font_names()
        pdf.setFont(bold,7.3)
        pdf.setFillColor(colors.HexColor("#243A30"))
        pdf.drawRightString(x+available-5,yy+7,text)
        pdf.setStrokeColor(colors.HexColor("#DEE6E2"))
        pdf.line(x+4,yy,x+available-4,yy)
    if overflow:
        _text(pdf,f"{overflow} confrontação(ões) adicional(is) no memorial",
              x+4,footer_y+29,size=6.4,color="#765A21")
    pdf.setStrokeColor(colors.HexColor("#D9E3DD"))
    pdf.line(x,footer_y+24,x+available,footer_y+24)
    _text(pdf,"PERÍMETRO TOTAL",x+3,footer_y+7,size=7.5,bold=True,color=accent)
    total=sum(float(seg["distance"]) for p in parcels for seg in p.segments)
    regular,bold,_=_font_names()
    pdf.setFont(bold,10)
    pdf.setFillColor(colors.HexColor(dark))
    pdf.drawRightString(x+available-4,footer_y+6,f"{_br_number(total,2)} m")


def reference_card(pdf,rect,zone,hemi,*,convergence=None,declination=None,
                   grid=None,palette):
    _box(pdf,rect,"SISTEMA DE REFERÊNCIA",palette)
    dark,pale,accent,_=palette
    meridian=zone*6-183
    data=[
        ("Datum","SIRGAS 2000"),
        ("Projeção",f"UTM · fuso {zone}{hemi}"),
        ("Meridiano central",f"{abs(meridian)}° {'W' if meridian<0 else 'E'}"),
        ("Convergência (c)",f"{convergence:+.4f}°" if convergence is not None else "não informada"),
        ("Declinação (d)",f"{declination:+.4f}°" if declination is not None else "não informada"),
        ("Grade",f"{_br_number(grid,0)} m" if grid is not None else "UTM"),
    ]
    x=rect.x+11
    width=rect.w-22
    step=(rect.h-35)/len(data)
    if step<15:
        raise ValueError("Área insuficiente para o sistema de referência.")
    for i,(k,v) in enumerate(data):
        y=rect.top-39-i*step
        _text(pdf,k,x,y,size=7,color="#62766D")
        regular,bold,_=_font_names()
        pdf.setFont(bold,7.2)
        pdf.setFillColor(colors.HexColor(dark))
        if pdfmetrics.stringWidth(v,bold,7.2)>width*.58:
            _text(pdf,v,x+width*.44,y,size=6.6,bold=True,color=dark,max_width=width*.54)
        else:
            pdf.drawRightString(x+width,y,v)
        pdf.setStrokeColor(colors.HexColor("#DEE6E2"))
        pdf.line(x,y-8,x+width,y-8)


def scale_card(pdf,rect,scale,palette,*,grid=None):
    _box(pdf,rect,"ESCALA NUMÉRICA",palette)
    dark,pale,accent,_=palette
    _text(pdf,f"1:{scale:,}".replace(",","."),rect.x+12,rect.top-62,
          size=15,bold=True,color=dark)
    inner=min(rect.w-30,185)
    from app.services.plant_template_engine import _pt_meter
    # Escolher medida "bonita" que cabe no cartão de forma física.
    pts_per_m=_pt_meter(scale)
    length_limit=inner
    raw=length_limit/pts_per_m
    magnitude=10**math.floor(math.log10(max(raw,1)))
    meters=max(v for v in (1,2,2.5,5,10) if v*magnitude<=raw)*magnitude
    length=meters*pts_per_m
    x=rect.x+13
    y=rect.y+37
    regular,bold,_=_font_names()
    for i in range(4):
        xx=x+i*length/4
        pdf.setFillColor(colors.HexColor(dark) if i%2==0 else colors.white)
        pdf.setStrokeColor(colors.HexColor(dark))
        pdf.rect(xx,y,length/4,6,stroke=1,fill=1)
        pdf.setFont(regular,6.3)
        pdf.setFillColor(colors.HexColor(dark))
        pdf.drawCentredString(xx,y+11,f"{meters*i/4:g}")
    pdf.drawCentredString(x+length,y+11,f"{meters:g} m")
    _text(pdf,f"Grade UTM: {_br_number(grid,0)} m" if grid is not None else "Grade UTM georreferenciada",
          x,rect.y+13,size=6.2,color="#63746C")


def compass_rose(pdf,cx,cy,r,palette):
    """Rosa cartográfica de 16 pontas, sem usar imagem raster."""
    dark,pale,accent,_=palette
    pdf.saveState()
    pdf.setStrokeColor(colors.HexColor(dark))
    pdf.setLineWidth(.65)
    pdf.circle(cx,cy,r,stroke=1,fill=0)
    pdf.circle(cx,cy,r*.82,stroke=1,fill=0)
    for i in range(72):
        a=math.pi/2-i*2*math.pi/72
        inner=r*(.78 if i%6==0 else .88 if i%3==0 else .93)
        pdf.line(cx+inner*math.cos(a),cy+inner*math.sin(a),
                 cx+r*.97*math.cos(a),cy+r*.97*math.sin(a))
    for i in range(16):
        a=math.pi/2-i*math.pi/8
        tip=r*(.73 if i%4==0 else .51 if i%2==0 else .36)
        side=r*.085 if i%4==0 else r*.048
        path=pdf.beginPath()
        path.moveTo(cx+tip*math.cos(a),cy+tip*math.sin(a))
        path.lineTo(cx+side*math.cos(a+math.pi/2),
                    cy+side*math.sin(a+math.pi/2))
        path.lineTo(cx,cy)
        path.lineTo(cx+side*math.cos(a-math.pi/2),
                    cy+side*math.sin(a-math.pi/2))
        path.close()
        pdf.setFillColor(colors.HexColor(dark) if i%2==0 else colors.white)
        pdf.drawPath(path,stroke=1,fill=1)
    regular,bold,_=_font_names()
    pdf.setFont(bold,9)
    pdf.setFillColor(colors.HexColor(accent))
    for label,a in (("N",math.pi/2),("L",0),("S",-math.pi/2),("O",math.pi)):
        pdf.drawCentredString(cx+(r+10)*math.cos(a),cy+(r+10)*math.sin(a)-3,label)
    pdf.restoreState()


def signature_card(pdf,rect,owner,owner_cpf,professional,palette,*,date_text=None,owner_rg=None):
    _box(pdf,rect,"QUADRO DE ASSINATURAS",palette)
    dark,pale,accent,_=palette
    x=rect.x+13
    width=rect.w-26
    compact=rect.h<245
    first=rect.top-42
    second=rect.top-(95 if compact else 112)
    def section(title,name,subtitle,y):
        _text(pdf,title,x,y,size=6.2,bold=True,color=accent)
        line_y=y-(25 if compact else 35)
        pdf.setStrokeColor(colors.HexColor("#526960"))
        pdf.line(x,line_y,x+width,line_y)
        _text(pdf,name or "Não informado",x+2,line_y-11,
              size=7.1,bold=True,color=dark,max_width=width-4)
        if subtitle:
            _text(pdf,subtitle,x+2,line_y-22,size=5.7,color="#687C71",
                  max_width=width-4)
    owner_docs=" | ".join(part for part in (
        f"CPF/CNPJ: {owner_cpf}" if owner_cpf else "",
        f"RG: {owner_rg}" if owner_rg else "") if part)
    section("PROPRIETÁRIO / DETENTOR",owner,
            owner_docs or "Documento não informado",first)
    details=[
        ("Profissão",professional.get("profession")),
        ("CREA/CAU",professional.get("crea") or professional.get("cau") or professional.get("registration_number")),
        ("Visto",professional.get("visto")),
        ("ART",professional.get("art")),
    ]
    prof_label=" | ".join(str(v).strip() for _,v in details if v)
    section("RESPONSÁVEL TÉCNICO",professional.get("full_name"),
            prof_label or "Registro e ART não informados",second)
    if not compact:
        box_y=rect.y+12
        box_h=min(55,max(32,rect.h-195))
        if box_y+box_h < second-52:
            pdf.setDash(4,3)
            pdf.setStrokeColor(colors.HexColor("#308467"))
            pdf.roundRect(x,box_y,width,box_h,6,stroke=1,fill=0)
            pdf.setDash()
            _text(pdf,"CARIMBO DO RESPONSÁVEL TÉCNICO",
                  x+12,box_y+box_h/2+3,size=6.1,bold=True,color="#308467",
                  max_width=width-24)
            if date_text:
                _text(pdf,"Elaborado em "+date_text,x+12,box_y+box_h/2-11,
                      size=6.0,color="#687C71")


def header_technical(pdf,w,h,zone,hemi,scale,date_text,palette,*,sheet="01",dark_text=False):
    dark,pale,accent,_=palette
    _,bold,_=_font_names()
    lines=[
        f"SIRGAS 2000 · UTM fuso {zone}{hemi}",
        f"Escala 1:{scale:,}".replace(",",".")+" · Folha "+sheet,
        "Data: "+(date_text or datetime.now().strftime("%d/%m/%Y")),
    ]
    pdf.setFillColor(colors.HexColor(dark if dark_text else "#FFFFFF"))
    for i,line in enumerate(lines):
        pdf.setFont(bold if i==0 else _font_names()[0],7 if i==0 else 6.4)
        pdf.drawRightString(w-43,h-58-i*15,line)
