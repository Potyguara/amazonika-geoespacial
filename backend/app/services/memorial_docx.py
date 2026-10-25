"""Memorial DOCX formatado com a mesma estrutura técnica da versão PDF."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from app.services.plant_memorial_v2 import Parcel, build_joint_memorial, DISCLAIMER, _br_number
from app.services.plant_memorial import load_document_template


GREEN = RGBColor(23, 75, 58)
DARK = RGBColor(28, 55, 43)
MUTED = RGBColor(85, 107, 95)


def _shade(cell, fill: str):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def _text(cell, value: str, bold=False, size=9, color=DARK):
    cell.text = ""
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run(str(value))
    r.bold = bold
    r.font.name = "Arial"
    r.font.size = Pt(size)
    r.font.color.rgb = color
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def _page_number(paragraph):
    run = paragraph.add_run("  |  Página ")
    run.font.size = Pt(7)
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    paragraph._p.append(field)


def build_memorial_docx(
    *, parcels: list[Parcel], title: str, memorial_heading: str,
    owner_name: str | None, owner_rg: str | None, owner_cpf: str | None,
    property_address: str | None, professional: dict, include_warning: bool,
) -> bytes:
    config = load_document_template()
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(1.75)
    section.bottom_margin = Cm(1.75)
    section.left_margin = Cm(2.25)
    section.right_margin = Cm(2.0)
    section.header_distance = Cm(.8)
    section.footer_distance = Cm(.8)

    normal = doc.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(9.5)
    normal.font.color.rgb = DARK
    normal.paragraph_format.line_spacing = 1.15
    normal.paragraph_format.space_after = Pt(3)

    # Documento técnico neutro: sem logomarca ou assinatura institucional.
    header = section.header.paragraphs[0]
    header.text = ""

    main_title = doc.add_paragraph()
    main_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    main_title.paragraph_format.space_after = Pt(3)
    r = main_title.add_run(memorial_heading.upper())
    r.bold = True
    r.font.size = Pt(15)
    r.font.color.rgb = GREEN

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.paragraph_format.space_after = Pt(14)
    r = sub.add_run(title.upper())
    r.bold = True
    r.font.size = Pt(10)
    r.font.color.rgb = DARK

    # Quadro compacto de identificação com colunas legíveis.
    table = doc.add_table(rows=0, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    table.columns[0].width = Cm(4.0)
    table.columns[1].width = Cm(12.3)
    attributes = [
        ("IMÓVEL", title),
        ("DETENTOR/POSSEIRO", owner_name or "Não informado"),
        ("RG / CPF", "  |  ".join(v for v in (owner_rg, owner_cpf) if v) or "Não informado"),
        ("LOCALIZAÇÃO", property_address or "Não informada"),
    ]
    for idx, (key, value) in enumerate(attributes):
        cells = table.add_row().cells
        cells[0].width, cells[1].width = Cm(4.0), Cm(12.3)
        _shade(cells[0], "DBE9DF")
        _shade(cells[1], "F6F9F7" if idx % 2 == 0 else "FFFFFF")
        _text(cells[0], key, bold=True, size=8, color=GREEN)
        _text(cells[1], value, size=9)
    doc.add_paragraph("").paragraph_format.space_after = Pt(0)

    summary = doc.add_table(rows=1, cols=2)
    summary.autofit = False
    summary.alignment = WD_TABLE_ALIGNMENT.CENTER
    data = [
        ("ÁREA TOTAL", f"{_br_number(sum(p.area_ha for p in parcels), 4)} ha"),
        ("PERÍMETRO TOTAL", f"{_br_number(sum(p.perimeter for p in parcels), 2)} m"),
    ]
    for cell, (label, value) in zip(summary.rows[0].cells, data):
        _shade(cell, "174B3A")
        cell.text = ""
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(3)
        r = p.add_run(label + "\n")
        r.bold = True
        r.font.size = Pt(7)
        r.font.color.rgb = RGBColor(216, 237, 219)
        v = p.add_run(value)
        v.bold = True
        v.font.size = Pt(10)
        v.font.color.rgb = RGBColor(255, 255, 255)

    narrative = build_joint_memorial(
        parcels, title=title, owner=owner_name,
        responsible=professional.get("full_name"), croqui=False,
        owner_rg=owner_rg, owner_cpf=owner_cpf,
        property_address=property_address,
        memorial_heading=memorial_heading, professional=professional,
    )
    start = narrative.find("DESCRIÇÃO DO PERÍMETRO")
    stop = narrative.find("________________________________________")
    lines = narrative[max(0, start):stop if stop >= 0 else None].splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        p = doc.add_paragraph()
        p.paragraph_format.widow_control = True
        p.paragraph_format.space_after = Pt(4)
        if line.startswith("DESCRIÇÃO DO PERÍMETRO"):
            p.paragraph_format.space_before = Pt(13)
            p.paragraph_format.space_after = Pt(7)
            p.paragraph_format.keep_with_next = True
            r = p.add_run(line)
            r.bold = True
            r.font.size = Pt(11)
            r.font.color.rgb = GREEN
        elif line.startswith("OBSERVAÇÃO:"):
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.keep_with_next = True
            r = p.add_run(line)
            r.bold = True
            r.font.color.rgb = GREEN
        else:
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            if line.startswith("Área:"):
                p.paragraph_format.keep_with_next = True
            r = p.add_run(line)
            if line.startswith("Área:"):
                r.bold = True

    # Assinatura sem página isolada por excesso de linhas em branco.
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(19)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run("________________________________________")
    fields = [
        professional.get("full_name") or "Responsável técnico",
        " — ".join(str(professional.get(k) or "") for k in
                   ("profession", "specialization") if professional.get(k)),
        " | ".join(str(professional.get(k) or "") for k in
                   ("crea", "visto", "incra_code") if professional.get(k)),
        f"ART: {professional['art']}" if professional.get("art") else "",
    ]
    visible = [line for line in fields if line]
    for i, line in enumerate(visible):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(1)
        p.paragraph_format.keep_with_next = i < len(visible)-1
        r = p.add_run(line)
        r.bold = i == 0
        r.font.size = Pt(9 if i == 0 else 8)

    foot = section.footer.paragraphs[0]
    foot.alignment = WD_ALIGN_PARAGRAPH.CENTER
    stamp = datetime.now(ZoneInfo("America/Belem")).strftime("%d/%m/%Y %H:%M:%S")
    if include_warning:
        warning = foot.add_run(DISCLAIMER)
        warning.font.size = Pt(6.3)
        warning.font.color.rgb = RGBColor(137, 47, 35)
        foot.add_run("\n")
    r = foot.add_run(f"Emitido: {stamp} - Horário de Belém")
    r.font.size = Pt(7)
    r.font.color.rgb = MUTED
    _page_number(foot)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
