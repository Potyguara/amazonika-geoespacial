from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo
from xml.etree import ElementTree as ET

from shapely.geometry import MultiPolygon, Polygon
from shapely.wkb import loads as load_wkb
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.analysis import Analysis


T = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
O = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
X = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"

TABLE = f"{{{T}}}"
OFFICE = f"{{{O}}}"
TEXT = f"{{{X}}}"

ET.register_namespace(
    "office",
    "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
)
ET.register_namespace(
    "table",
    "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
)
ET.register_namespace(
    "text",
    "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
)
ET.register_namespace(
    "style",
    "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
)
ET.register_namespace(
    "fo",
    "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
)
ET.register_namespace(
    "svg",
    "urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0",
)
ET.register_namespace(
    "xlink",
    "http://www.w3.org/1999/xlink",
)
ET.register_namespace(
    "dc",
    "http://purl.org/dc/elements/1.1/",
)
ET.register_namespace(
    "meta",
    "urn:oasis:names:tc:opendocument:xmlns:meta:1.0",
)
ET.register_namespace(
    "number",
    "urn:oasis:names:tc:opendocument:xmlns:datastyle:1.0",
)
ET.register_namespace(
    "of",
    "urn:oasis:names:tc:opendocument:xmlns:of:1.2",
)


def _template_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "templates"
        / "sigef"
        / "modelo_sigef.ods"
    )


def _sheet(root: ET.Element, name: str) -> ET.Element:
    for sheet in root.findall(f".//{TABLE}table"):
        if sheet.attrib.get(f"{TABLE}name") == name:
            return sheet

    raise ValueError(f"Aba {name!r} não encontrada no modelo SIGEF.")


def _expand_row_cells(row: ET.Element) -> list[ET.Element]:
    expanded: list[ET.Element] = []

    for child in list(row):
        if child.tag not in {
            f"{TABLE}table-cell",
            f"{TABLE}covered-table-cell",
        }:
            continue

        repeat = int(
            child.attrib.get(
                f"{TABLE}number-columns-repeated",
                "1",
            )
        )

        for _ in range(repeat):
            cell = deepcopy(child)
            cell.attrib.pop(
                f"{TABLE}number-columns-repeated",
                None,
            )
            expanded.append(cell)

    for child in list(row):
        row.remove(child)

    for cell in expanded:
        row.append(cell)

    return expanded


def _set_string(cell: ET.Element, value: str) -> None:
    for child in list(cell):
        if child.tag == f"{TEXT}p":
            cell.remove(child)

    cell.attrib.pop(f"{OFFICE}value", None)
    cell.attrib.pop(f"{OFFICE}date-value", None)
    cell.attrib.pop(f"{OFFICE}boolean-value", None)
    cell.set(f"{OFFICE}value-type", "string")

    paragraph = ET.SubElement(cell, f"{TEXT}p")
    paragraph.text = value


def _set_number(cell: ET.Element, value: float) -> None:
    for child in list(cell):
        if child.tag == f"{TEXT}p":
            cell.remove(child)

    cell.attrib.pop(f"{OFFICE}string-value", None)
    cell.attrib.pop(f"{OFFICE}date-value", None)
    cell.attrib.pop(f"{OFFICE}boolean-value", None)

    cell.set(f"{OFFICE}value-type", "float")
    cell.set(f"{OFFICE}value", f"{value:.10f}")

    paragraph = ET.SubElement(cell, f"{TEXT}p")
    paragraph.text = f"{value:.10f}".rstrip("0").rstrip(".") or "0"


def _set_identification_value(
    sheet: ET.Element,
    row_number: int,
    column_number: int,
    value: str,
) -> None:
    rows = sheet.findall(f"{TABLE}table-row")

    if row_number < 1 or row_number > len(rows):
        raise ValueError(
            f"Linha {row_number} inexistente na identificação."
        )

    row = rows[row_number - 1]
    cells = _expand_row_cells(row)

    if column_number < 1 or column_number > len(cells):
        raise ValueError(
            f"Coluna {column_number} inexistente na linha {row_number}."
        )

    _set_string(cells[column_number - 1], value)


def _extract_polygon(
    db: Session,
    analysis: Analysis,
) -> Polygon:
    geom_wkb = db.scalar(
        select(
            func.ST_AsBinary(
                func.ST_Force2D(Analysis.input_geom)
            )
        ).where(Analysis.id == analysis.id)
    )

    if not geom_wkb:
        raise ValueError("Geometria da análise não encontrada.")

    geometry = load_wkb(bytes(geom_wkb))

    if isinstance(geometry, Polygon):
        polygon = geometry

    elif isinstance(geometry, MultiPolygon):
        polygons = list(geometry.geoms)

        if len(polygons) != 1:
            raise ValueError(
                "A simulação SIGEF, nesta versão, aceita apenas "
                "um polígono contínuo."
            )

        polygon = polygons[0]

    else:
        raise ValueError(
            "A ODS SIGEF somente pode ser criada para uma área poligonal."
        )

    if polygon.is_empty or not polygon.is_valid:
        raise ValueError(
            "A geometria da análise não é um polígono válido."
        )

    if len(polygon.interiors) > 0:
        raise ValueError(
            "A simulação SIGEF, nesta versão, não aceita polígonos "
            "com ilhas ou vazios internos."
        )

    return polygon



def _decimal_to_dms(value: float, axis: str) -> str:
    """Converte grau decimal para o texto geográfico aceito pelo SIGEF.

    Exemplo do modelo validado:
        longitude: 51 13 27,694 W
        latitude:  01 04 59,070 N
    """
    absolute = abs(float(value))
    degrees = int(absolute)
    minutes_float = (absolute - degrees) * 60.0
    minutes = int(minutes_float)
    seconds = round((minutes_float - minutes) * 60.0, 3)

    # Corrige eventual transporte de arredondamento.
    if seconds >= 60.0:
        seconds = 0.0
        minutes += 1
    if minutes >= 60:
        minutes = 0
        degrees += 1

    axis = axis.lower()
    if axis == "lon":
        hemisphere = "W" if value < 0 else "E"
    elif axis == "lat":
        hemisphere = "S" if value < 0 else "N"
    else:
        raise ValueError("Eixo inválido para conversão GMS.")

    degree_text = f"{degrees:02d}"
    second_text = f"{seconds:06.3f}".replace(".", ",")
    return f"{degree_text} {minutes:02d} {second_text} {hemisphere}"


def _municipalities_for_analysis(db: Session, analysis: Analysis) -> list[str]:
    """Retorna os municípios efetivamente interceptados pelo imóvel.

    A tabela ibge_municipios_2025 é uma referência estrutural do sistema,
    independente das camadas que o usuário liga/desliga para a análise.
    Interseções meramente lineares/de fronteira (<= 1 m²) são descartadas.
    """
    exists = db.scalar(text("SELECT to_regclass('public.ibge_municipios_2025')"))
    if not exists:
        return []

    rows = db.execute(
        text(
            """
            SELECT
                m.nm_mun,
                m.sigla_uf,
                ST_Area(
                    ST_Intersection(m.geom, a.input_geom)::geography
                ) AS intersection_area_m2
            FROM ibge_municipios_2025 AS m
            JOIN analyses AS a
              ON a.id = :analysis_id
            WHERE ST_Intersects(m.geom, a.input_geom)
              AND ST_Area(
                    ST_Intersection(m.geom, a.input_geom)::geography
                  ) > 1.0
            ORDER BY intersection_area_m2 DESC, m.nm_mun
            """
        ),
        {"analysis_id": str(analysis.id)},
    ).all()

    result: list[str] = []
    seen: set[str] = set()
    for name, uf, _area in rows:
        label = f"{str(name).strip()}-{str(uf).strip().upper()}"
        if label and label not in seen:
            seen.add(label)
            result.append(label)
    return result

def _write_perimeter(
    sheet: ET.Element,
    polygon: Polygon,
) -> None:
    rows = sheet.findall(f"{TABLE}table-row")

    if len(rows) < 12:
        raise ValueError(
            "O modelo SIGEF não possui a linha base de vértices."
        )

    # O modelo SIGEF validado usa coordenadas geográficas em GMS.
    _set_identification_value(
        sheet,
        9,
        2,
        "Geográfica",
    )

    # Cabeçalho do perímetro.
    _set_identification_value(
        sheet,
        3,
        2,
        "SIMULAÇÃO",
    )

    # A função acima trabalha com a aba fornecida e serve também
    # para o perímetro, pois usa apenas linha/coluna.
    _set_identification_value(
        sheet,
        4,
        2,
        "001",
    )

    base_row = rows[11]
    base_row.attrib.pop(
        f"{TABLE}number-rows-repeated",
        None,
    )

    base_cells = _expand_row_cells(base_row)

    if len(base_cells) < 12:
        raise ValueError(
            "Linha de vértices do modelo possui menos de 12 colunas."
        )

    coordinates = list(polygon.exterior.coords)

    # O fechamento do anel repete o primeiro ponto. A planilha de
    # perímetro deve listar cada vértice apenas uma vez.
    if (
        len(coordinates) > 1
        and coordinates[0] == coordinates[-1]
    ):
        coordinates = coordinates[:-1]

    if len(coordinates) < 3:
        raise ValueError(
            "O polígono possui quantidade insuficiente de vértices."
        )

    parent = sheet
    base_index = list(parent).index(base_row)

    parent.remove(base_row)

    for index, coordinate in enumerate(coordinates, start=1):
        longitude = float(coordinate[0])
        latitude = float(coordinate[1])

        row = deepcopy(base_row)
        cells = _expand_row_cells(row)

        _set_string(
            cells[0],
            f"SIMU-P-{index:07d}",
        )
        _set_string(cells[1], _decimal_to_dms(longitude, "lon"))
        _set_number(cells[2], 0.0)
        _set_string(cells[3], _decimal_to_dms(latitude, "lat"))
        _set_number(cells[4], 0.0)
        _set_number(cells[5], 0.0)
        _set_number(cells[6], 0.0)
        _set_string(cells[7], "PG1")
        _set_string(cells[8], "LA1")
        _set_string(cells[9], "")
        _set_string(cells[10], "")
        _set_string(
            cells[11],
            "TERRAS A QUEM DE DIREITO",
        )

        parent.insert(
            base_index + index - 1,
            row,
        )


def build_sigef_simulation_ods(
    db: Session,
    analysis: Analysis,
) -> bytes:
    if analysis.status != "COMPLETED":
        raise ValueError(
            "A análise precisa estar concluída para gerar a ODS."
        )

    polygon = _extract_polygon(db, analysis)

    template = _template_path()

    if not template.exists():
        raise ValueError(
            "Modelo oficial SIGEF não encontrado no servidor."
        )

    with ZipFile(template, "r") as source:
        content_xml = source.read("content.xml")
        root = ET.fromstring(content_xml)

        identification = _sheet(root, "identificacao")
        perimeter = _sheet(root, "perimetro_1")

        subject = dict(analysis.subject_json or {})
        holder_name = str(subject.get("holder_name") or "SIMULAÇÃO").strip() or "SIMULAÇÃO"
        holder_document = "".join(
            character
            for character in str(subject.get("holder_document") or "")
            if character.isdigit()
        )
        holder_kind = "Jurídica" if len(holder_document) == 14 else "Física"

        # Preenchimento mínimo para SIMULAÇÃO.
        _set_identification_value(
            identification,
            2,
            2,
            "Particular",
        )
        _set_identification_value(
            identification,
            5,
            2,
            holder_kind,
        )
        _set_identification_value(
            identification,
            6,
            2,
            holder_name,
        )
        _set_identification_value(
            identification,
            7,
            2,
            holder_document,
        )
        _set_identification_value(
            identification,
            10,
            2,
            "SIMULAÇÃO",
        )
        _set_identification_value(
            identification,
            11,
            2,
            "Área não Titulada",
        )
        _set_identification_value(
            identification,
            12,
            2,
            "Particular",
        )
        _set_identification_value(
            identification,
            13,
            2,
            "",
        )
        _set_identification_value(
            identification,
            14,
            2,
            "",
        )
        _set_identification_value(
            identification,
            15,
            2,
            "",
        )

        municipalities = _municipalities_for_analysis(db, analysis)
        if not municipalities:
            raise ValueError(
                "Malha municipal IBGE 2025 não carregada ou imóvel sem município identificado."
            )

        # O SIGEF aceita múltiplos municípios na linha Município(s).
        # Preenche um município por célula, sem limite de quantidade.
        # Quando houver apenas um município, repetimos A/B para manter
        # compatibilidade com o modelo já validado no simulador.
        municipality_values = list(municipalities)
        if len(municipality_values) == 1:
            municipality_values.append(municipality_values[0])

        identification_rows = identification.findall(f"{TABLE}table-row")
        if len(identification_rows) < 17:
            raise ValueError("Linha Município(s) não encontrada no modelo SIGEF.")

        municipality_row = identification_rows[16]
        municipality_cells = _expand_row_cells(municipality_row)
        if not municipality_cells:
            raise ValueError("A linha Município(s) não possui células utilizáveis.")

        # Expande a própria linha se a quantidade de municípios exceder
        # o número de células originalmente existentes no modelo.
        while len(municipality_cells) < len(municipality_values):
            template_cell = deepcopy(municipality_cells[-1])
            _set_string(template_cell, "")
            municipality_row.append(template_cell)
            municipality_cells.append(template_cell)

        for index, municipality in enumerate(municipality_values):
            _set_string(municipality_cells[index], municipality)

        # Limpa células remanescentes da linha para não carregar conteúdo
        # residual do modelo quando houver menos municípios que células.
        for index in range(len(municipality_values), len(municipality_cells)):
            _set_string(municipality_cells[index], "")

        _write_perimeter(
            perimeter,
            polygon,
        )

        new_content = ET.tostring(
            root,
            encoding="utf-8",
            xml_declaration=True,
        )

        output = BytesIO()

        with ZipFile(output, "w") as target:
            for item in source.infolist():
                data = (
                    new_content
                    if item.filename == "content.xml"
                    else source.read(item.filename)
                )

                info = ZipInfo(
                    filename=item.filename,
                    date_time=item.date_time,
                )

                info.comment = item.comment
                info.extra = item.extra
                info.internal_attr = item.internal_attr
                info.external_attr = item.external_attr
                info.create_system = item.create_system

                # O mimetype precisa permanecer sem compressão e
                # ser o primeiro arquivo do pacote ODS.
                if item.filename == "mimetype":
                    info.compress_type = ZIP_STORED
                else:
                    info.compress_type = ZIP_DEFLATED

                target.writestr(info, data)

        return output.getvalue()
