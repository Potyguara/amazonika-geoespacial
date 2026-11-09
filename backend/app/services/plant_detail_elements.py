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
    """Quadro sem colisões: a altura de cada linha segue o texto medido."""
    groups=group_confrontations(parcels)
    _box(pdf,rect,"CONFRONTAÇÕES",palette)
    dark,pale,accent,_=palette
    x=rect.x+9
    available=rect.w-18
    ext_w=max(53,available*.18)
    stretch=available-ext_w
    name_w=stretch*.58
    segment_w=stretch-name_w
    top=rect.top-32
    pdf.setFillColor(colors.HexColor("#EFF5F1"))
    pdf.rect(x,top-22,available,22,fill=1,stroke=0)
    _text(pdf,"CONFRONTANTE",x+4,top-15,size=6.7,bold=True,color=dark)
    _text(pdf,"TRECHO",x+name_w+4,top-15,size=6.7,bold=True,color=dark)
    _text(pdf,"EXT. (m)",x+name_w+segment_w+3,top-15,size=6.7,bold=True,color=dark)
    regular,bold,_=_font_names()
    def rows_at(font_size):
        result=[]
        for group in groups:
            name=str(group["name"])
            import re
            def brief(vertex):
                return re.sub(r"^.*?-(?=[MV]-)", "", str(vertex))
            segment=f'{brief(group["start"])} – {brief(group["end"])}'
            name_style=ParagraphStyle("name",fontName=bold,fontSize=font_size,
                                      leading=font_size+2.1,textColor=colors.HexColor("#243A30"))
            segment_style=ParagraphStyle("seg",fontName=regular,fontSize=font_size-.25,
                                         leading=font_size+2,textColor=colors.HexColor("#53685E"))
            name_para=Paragraph(escape(name),name_style)
            seg_para=Paragraph(escape(segment),segment_style)
            _,name_h=name_para.wrap(name_w-10,500)
            _,seg_h=seg_para.wrap(segment_w-10,500)
            row_h=max(name_h,seg_h,font_size+3)+9
            result.append((group,name_para,seg_para,name_h,seg_h,row_h))
        return result
    footer_top=rect.y+39
    max_body=(top-24)-footer_top
    size=7.2
    rows=rows_at(size)
    while sum(item[5] for item in rows)>max_body and size>5.6:
        size=round(size-.2,2)
        rows=rows_at(size)
    y=top-24
    remaining=0
    for i,(group,name_para,seg_para,name_h,seg_h,row_h) in enumerate(rows):
        if y-row_h<footer_top:
            remaining=len(rows)-i
            break
        name_para.drawOn(pdf,x+4,y-5-name_h)
        seg_para.drawOn(pdf,x+name_w+4,y-5-seg_h)
        pdf.setFont(bold,max(6.3,size))
        pdf.setFillColor(colors.HexColor("#243A30"))
        pdf.drawRightString(x+available-4,y-8-max(name_h,seg_h)/2,
                            _br_number(group["distance"],2))
        y-=row_h
        pdf.setStrokeColor(colors.HexColor("#DEE6E2"))
        pdf.line(x+4,y+1,x+available-4,y+1)
    if remaining:
        _text(pdf,f"Mais {remaining} confrontação(ões) no memorial descritivo",
              x+4,footer_top-8,size=6,color="#765A21",max_width=available-8)
    pdf.setStrokeColor(colors.HexColor("#D9E3DD"))
    pdf.line(x,rect.y+34,x+available,rect.y+34)
    _text(pdf,"PERÍMETRO TOTAL",x+3,rect.y+17,size=7.4,bold=True,color=accent)
    total=sum(float(seg["distance"]) for p in parcels for seg in p.segments)
    pdf.setFont(bold,10)
    pdf.setFillColor(colors.HexColor(dark))
    pdf.drawRightString(x+available-4,rect.y+15,f"{_br_number(total,2)} m")


def reference_card(pdf,rect,zone,hemi,*,convergence=None,declination=None,
                   grid=None,palette,magnetic_source=None):
    _box(pdf,rect,"SISTEMA DE REFERÊNCIA",palette)
    dark,pale,accent,_=palette
    meridian=zone*6-183
    data=[
        ("Datum","SIRGAS 2000"),
        ("Projeção",f"UTM · fuso {zone}{hemi}"),
        ("Meridiano central",f"{abs(meridian)}° {'W' if meridian<0 else 'E'}"),
        ("Convergência (c)",f"{convergence:+.4f}°" if convergence is not None else "não informada"),
        ("Declinação (d)",(f"{declination:+.3f}° · " + ("WMM2025" if magnetic_source and "WMM2025" in magnetic_source else "RT")) if declination is not None else "não informada"),
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


def signature_card(pdf,rect,owner,owner_cpf,professional,palette,
                   *,date_text=None,owner_rg=None):
    """Assinaturas: cada dado em linha própria, sem comprimir ou sobrepor."""
    _box(pdf,rect,"QUADRO DE ASSINATURAS",palette)
    dark,pale,accent,_=palette
    x=rect.x+12
    width=rect.w-24
    regular,bold,_=_font_names()
    # A largura real do cartão define quantas linhas cada informação ocupa.
    entries=[
        ("PROPRIETÁRIO / DETENTOR",str(owner or "Não informado"),[
            ("CPF/CNPJ",owner_cpf),("RG",owner_rg),
        ]),
        ("RESPONSÁVEL TÉCNICO",str(professional.get("full_name") or "Não informado"),[
            ("Profissão",professional.get("profession")),
            ("Especialidade",professional.get("specialization") or professional.get("specialty")),
            ("CREA/CAU",professional.get("crea") or professional.get("cau") or professional.get("registration_number")),
            ("Visto",professional.get("visto")),
            ("INCRA",professional.get("incra_code")),
            ("ART",professional.get("art")),
        ]),
    ]
    def paragraph(value,bold_text=False):
        style=ParagraphStyle("signature_info",fontName=bold if bold_text else regular,
                              fontSize=7.0 if bold_text else 6.3,
                              leading=9.5 if bold_text else 8.1,
                              textColor=colors.HexColor(dark if bold_text else "#586C62"))
        p=Paragraph(escape(str(value)),style)
        _,height=p.wrap(width-3,1000)
        return p,height
    prepared=[]
    for section,name,details in entries:
        fields=[(k,str(v).strip()) for k,v in details if v is not None and str(v).strip()]
        name_p,name_h=paragraph(name,True)
        items=[paragraph(f"{label}: {value}") for label,value in fields]
        block_h=13+name_h+sum(h+2 for _,h in items)+6
        prepared.append((section,name_p,name_h,items,block_h))
    available=rect.h-39-14
    required=sum(v[4] for v in prepared)+16
    # Se não houver altura suficiente, reservar ampliação no layout em vez
    # de desenhar linhas por cima de outros campos.
    if required>available:
        # Mostrar dados completos até onde houver espaço, mas nunca colidir:
        # o chamador deve adaptar a altura do painel conforme a orientação.
        font_note=6.0
    y=rect.top-38
    for section,name_p,name_h,items,block_h in prepared:
        if y-block_h < rect.y+13:
            _text(pdf,"Dados adicionais do responsável técnico no memorial",
                  x,rect.y+14,size=5.7,color="#586C62",max_width=width)
            break
        pdf.setFont(bold,6.5)
        pdf.setFillColor(colors.HexColor(accent))
        pdf.drawString(x,y,section)
        y-=16
        pdf.setStrokeColor(colors.HexColor("#71877C"))
        pdf.line(x,y,x+width,y)
        y-=name_h+3
        name_p.drawOn(pdf,x+1,y)
        for p,height in items:
            y-=height+2
            p.drawOn(pdf,x+1,y)
        y-=14
    # Carimbo apenas quando existir espaço real e livre.
    if y-40 >= rect.y+12:
        pdf.setDash(3,3)
        pdf.setStrokeColor(colors.HexColor("#308467"))
        pdf.roundRect(x,rect.y+9,width,min(40,y-rect.y-19),4,stroke=1,fill=0)
        pdf.setDash()
        _text(pdf,"CARIMBO DO RESPONSÁVEL TÉCNICO",
              x+9,rect.y+23,size=6.2,bold=True,color="#308467")
    if date_text:
        _text(pdf,"Elaborado em "+date_text,x,rect.y+4,size=5.6,color="#65786C")


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
