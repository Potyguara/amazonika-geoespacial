from __future__ import annotations

from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt

from app.services.plant_memorial_v2 import Parcel, build_joint_memorial
from app.services.plant_memorial import load_document_template


def build_memorial_docx(
    *,
    parcels: list[Parcel],
    title: str,
    memorial_heading: str,
    owner_name: str | None,
    owner_rg: str | None,
    owner_cpf: str | None,
    property_address: str | None,
    professional: dict,
    include_warning: bool,
) -> bytes:
    config = load_document_template()
    document = Document()
    section = document.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.2)

    normal = document.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(10)
    normal.paragraph_format.space_after = Pt(6)

    header = section.header.paragraphs[0]
    header.text = str(config.get("company_name") or "Amazônika Engenharia")
    header.style = document.styles["Heading 2"]
    header.alignment = WD_ALIGN_PARAGRAPH.CENTER

    heading = document.add_heading(memorial_heading.upper(), level=1)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    document.add_paragraph(title).alignment = WD_ALIGN_PARAGRAPH.CENTER

    content = build_joint_memorial(
        parcels, title=title, owner=owner_name,
        responsible=professional.get("full_name"), croqui=include_warning,
        owner_rg=owner_rg, owner_cpf=owner_cpf,
        property_address=property_address,
        memorial_heading=memorial_heading,
        professional=professional,
    )
    lines = content.splitlines()
    # Cabeçalho visual acima evita repetição literal do título.
    for line in lines[1:]:
        if not line.strip():
            document.add_paragraph("")
            continue
        if line.startswith("DESCRIÇÃO DO PERÍMETRO"):
            document.add_heading(line, level=2)
        elif line.startswith("OBSERVAÇÃO:"):
            document.add_heading(line, level=2)
        else:
            paragraph = document.add_paragraph(line)
            paragraph.paragraph_format.widow_control = True

    footer = section.footer.paragraphs[0]
    footer.text = (
        f"{config.get('document_footer') or 'Documento técnico gerado pelo Amazônika Geoespacial.'} | "
        f"Gerado em {datetime.now(ZoneInfo('America/Belem')):%d/%m/%Y %H:%M:%S} (Belém)"
    )
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in footer.runs:
        run.font.size = Pt(7)

    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()
