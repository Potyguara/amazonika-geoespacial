"""Memoriais A/B/C baseados nos três modelos profissionais fornecidos.

Renderização vetorial A4: identificação, confrontações, croqui e narrativa
geodésica agrupada. O fluxo de edição livre continua no renderer legado.
"""
from __future__ import annotations

import math
from datetime import date
import re
from xml.sax.saxutils import escape
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER
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


def _col(value):
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


def _para(text,size=8,leading=11,color="#34483D",bold=False,justify=False):
    style=ParagraphStyle("memorial_tpl",fontName="Helvetica-Bold" if bold else "Helvetica",
                         fontSize=size,leading=leading,textColor=_col(color),
                         splitLongWords=0,
                         alignment=TA_JUSTIFY if justify else TA_LEFT)
    return Paragraph(text,style)


def _remove_redundant_auto_header(value):
    """Remove só o prólogo gerado que já foi impresso no quadro cadastral."""
    lines=value.strip().splitlines()
    if not lines or lines[0].strip().upper()!="MEMORIAL DESCRITIVO":
        return value.strip()
    for i,line in enumerate(lines):
        if line.strip().upper().startswith("DESCRIÇÃO DO PERÍMETRO - "):
            remainder="\n".join(lines[i+1:]).strip()
            if remainder.lower().startswith("inicia-se a descrição"):
                return remainder
    return value.strip()


def _without_legacy_signature(value,professional):
    """Evita duplicar um rodapé automático antigo, sem remover prosa técnica.

    Só atua quando existe um separador longo de assinatura seguido do
    mesmo profissional cadastrado; títulos e corpo permanecem intocados.
    """
    text=value.strip()
    found=list(re.finditer(r"_{20,}",text))
    name=str(professional.get("full_name") or "").strip()
    if not found or not name:
        return text
    pos=found[-1].start()
    remainder=text[pos:]
    if name.casefold() in remainder.casefold() and len(remainder)<1200:
        return text[:pos].rstrip()
    return text


def _highlight_memorial_text(value,confrontants):
    """Confrontantes e vértices com destaque, sem aceitar HTML bruto."""
    source=escape(value)
    patterns=[(escape(name), "#176746") for name in
              sorted({n.strip() for n in confrontants if n.strip()},
                     key=len,reverse=True)]
    patterns.append((None,"#186C52"))
    tokens=[]
    for name,color in patterns:
        regex=(re.compile(re.escape(name),re.I) if name else
               re.compile(r"(?<![\w-])(?:[A-Z0-9]+-)?[MV]-\d{2,6}(?![\w-])",re.I))
        def mark(match):
            token=f"@@HL{len(tokens)}@@"
            tokens.append(f'<font color="{color}"><b>{match.group(0)}</b></font>')
            return token
        source=regex.sub(mark,source)
    for i,value in enumerate(tokens):
        source=source.replace(f"@@HL{i}@@",value)
    return source


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
    if len(groups)>6:
        _str(pdf,"Demais confrontantes descritos nas próximas seções",
             x+10,footer+16,5.6,color="#78521D")
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
        y=H-125  # Respeitar inclusive o cabeçalho alto do modelo moderno

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

    def confrontation_banner(number, group):
        nonlocal y
        # Nome completo: cabeçalho cresce conforme a quebra real de linhas.
        name_para=_para(escape("Confrontante: "+str(group["name"])),
                        size=8.4,leading=10.7,color="#FFFFFF",bold=True)
        _,name_h=name_para.wrap(W-2*margin-79,300)
        bar_h=max(43,name_h+29)
        if y<bar_h+180:
            new_page()
        pdf.setFillColor(_col(c["primary"]))
        pdf.roundRect(margin,y-bar_h,W-2*margin,bar_h,5,stroke=0,fill=1)
        pdf.setFillColor(_col(c["gold"]))
        pdf.rect(margin,y-bar_h,5,bar_h,stroke=0,fill=1)
        pdf.circle(margin+24,y-17,10,stroke=0,fill=1)
        _str(pdf,str(number),margin+24,y-20,8,"Helvetica-Bold",
             c["primary"],center=True)
        name_para.drawOn(pdf,margin+42,y-10-name_h)
        subtitle=(f"{_short(group['start'])} → {_short(group['end'])} · "
                  f"{_br_number(group['distance'],2)} m")
        _str(pdf,subtitle,W-margin-11,y-bar_h+9,7.0,
             "Helvetica-Bold","#FFFFFF",right=True)
        y-=bar_h+13

    def narrative(html,*,keep_min=18,space=7):
        nonlocal y
        pending=_para(html,size=8.1,leading=12.4,color=c["dark"],justify=True)
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

    if edited_memorial is not None and edited_memorial.strip():
        # Manter revisão do usuário, eliminando somente prólogo padrão duplicado.
        source=_without_legacy_signature(
            _remove_redundant_auto_header(edited_memorial),professional
        )
        confrontants=[name for p in parcels for name in p.confrontants]
        # A descrição editada mantém seu conteúdo, mas cada transição
        # explícita de confrontante recebe a mesma faixa dos textos gerados.
        chains=group_confrontations(parcels)
        parts=re.split(
            r"(?i)(?=deste,?\s+segue\s+confrontando\s+com\s+)",
            source,
        )
        banner_number=0
        for part in parts:
            for block in re.split(r"\n\s*\n",part):
                text=" ".join(line.strip() for line in block.splitlines()
                              if line.strip())
                if not text:
                    continue
                is_transition=re.match(
                    r"(?i)^deste,?\s+segue\s+confrontando\s+com\s+",
                    text,
                )
                if is_transition:
                    for group in chains:
                        prefix=text[is_transition.end():]
                        if prefix.casefold().startswith(str(group["name"]).casefold()):
                            banner_number+=1
                            confrontation_banner(banner_number,group)
                            break
                narrative(_highlight_memorial_text(text,confrontants),space=10)
    else:
        for p_index,parcel in enumerate(parcels):
            if p_index:
                if y<120:new_page()
                _str(pdf,f"POLÍGONO {p_index+1}",margin,y,8,"Helvetica-Bold",c["primary"])
                y-=21
            starting=parcel.segments[0]
            alt=parcel.altitudes[0]
            altpart=f" e Altitude: {_br_number(alt,2)} m" if alt is not None else ""
            intro=(f"Inicia-se a descrição deste perímetro no vértice <font color='#186C52'><b>{escape(starting['start'])}</b></font>, "
                   f"de coordenadas (Longitude: {_dms(starting['lon'],'lon')}, "
                   f"Latitude: {_dms(starting['lat'],'lat')}{altpart}); linha ideal.")
            narrative(intro,space=13)
            groups=group_confrontations([parcel])
            for idx,group in enumerate(groups):
                confrontation_banner(idx+1,group)
                prose=(f"Deste, segue confrontando com <font color='#176746'><b>{escape(group['name'])}</b></font>, "
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
                            f"<font color='#186C52'><b>{escape(seg['end'])}</b></font>, {ending}; ")
                narrative(prose.rstrip("; ")+("; linha ideal;" if idx<len(groups)-1 else "."),space=12)
            narrative(f"<b>ÁREA DESTA PARCELA:</b> {_br_number(parcel.area_ha,4)} ha · "
                      f"<b>PERÍMETRO:</b> {_br_number(parcel.perimeter,2)} m",space=10)
        if croqui:
            narrative("Coordenadas referenciadas ao SIRGAS 2000; azimutes e distâncias "
                      "geodésicos calculados sobre o elipsóide GRS80. A precisão depende "
                      "da fonte da geometria; esta emissão não constitui certificação fundiária.",
                      space=13)
    # Assinaturas: duas colunas independentes, alturas calculadas.
    # Não repetir dados cadastrais em texto avulso antes das assinaturas.
    signature_width=(W-2*margin-18)/2
    def sign_block(title,name,details):
        prepared=[]
        for value,bold_text in [(name,True),*[(entry,False) for entry in details]]:
            item=_para(escape(value),size=7.0 if bold_text else 6.4,
                       leading=9.6 if bold_text else 9.0,color=c["dark"],
                       bold=bold_text)
            item.style.alignment=TA_CENTER
            _,height=item.wrap(signature_width-8,800)
            prepared.append((item,height))
        block_height=13+40+sum(h+7 for _,h in prepared)+12
        return title,prepared,block_height
    owner_details=[
        f"CPF/CNPJ: {owner_cpf}" if owner_cpf else "CPF/CNPJ não informado",
    ]
    if owner_rg:
        owner_details.append(f"RG: {owner_rg}")
    tech_details=[
        f"{label}: {professional[k]}" for k,label in (
            ("profession","Profissão"),
            ("specialization","Especialidade"),
            ("crea","CREA/CAU"),
            ("visto","Visto"),
            ("incra_code","INCRA"),
            ("art","ART"),
        ) if professional.get(k)
    ]
    signatures=[
        sign_block("PROPRIETÁRIO / DETENTOR",owner or "Não informado",
                   owner_details),
        sign_block("RESPONSÁVEL TÉCNICO",
                   professional.get("full_name") or "Não informado",
                   tech_details),
    ]
    signature_height=max(item[2] for item in signatures)+25
    if y<signature_height+76:
        new_page()
    location_date=f"{address or 'Local não informado'}, {survey_date.strftime('%d/%m/%Y')}."
    y-=_fit_para(pdf,location_date,margin,y,W-2*margin,
                 size=7.2,leading=9.1,color=c["dark"])+17
    for i,(label,items,_) in enumerate(signatures):
        xx=margin+i*(signature_width+18)
        _str(pdf,label,xx+signature_width/2,y,6.7,"Helvetica-Bold",
             c["gold"],center=True)
        line_y=y-45
        pdf.setStrokeColor(_col(c["primary"]))
        pdf.line(xx,line_y,xx+signature_width,line_y)
        current=line_y-14
        for paragraph,height in items:
            paragraph.drawOn(pdf,xx+4,current-height)
            current-=height+7
    # Reservar altura até o maior bloco de qualificações para o rodapé.
    footer()
