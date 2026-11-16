"""GEO99: planilha ODS de TRABALHO, nunca apropriada para submissão direta ao SIGEF.

Preserva coordenadas, nomes e atributos efetivamente informados. Campos ausentes
(h elipsoidal, desvios padrão, etc.) ficam em branco. Não estima nem inventa.
Inclui aba de aviso explícito para impedir confusão com planilha certificável.
"""
from __future__ import annotations
from copy import deepcopy
from io import BytesIO
from math import isfinite
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZipInfo, ZIP_STORED, ZIP_DEFLATED

from app.services.sigef_ods import (
    TABLE, OFFICE, TEXT, _sheet, _template_path,
    _expand_row_cells, _set_identification_value,
    _set_number, _set_string, _decimal_to_dms,
)


def _optional_number(value):
    if value is None or isinstance(value, bool) or str(value).strip() == "":
        return None
    try:
        result = float(str(value).replace(",", "."))
    except (ValueError, TypeError) as exc:
        raise ValueError("Campo numérico inválido na planilha de trabalho.") from exc
    if not isfinite(result):
        raise ValueError("Número não finito na planilha de trabalho.")
    return result


def _write_draft_perimeter(sheet, parcel, pos):
    vertices = parcel.get("vertices") or []
    if not 3 <= len(vertices) <= 2000:
        raise ValueError("A parcela deve conter entre 3 e 2000 vértices.")
    _set_identification_value(sheet, 3, 2, str(parcel.get("name") or "PARCELA EM REVISÃO")[:120])
    _set_identification_value(sheet, 4, 2, str(parcel.get("number") or pos))
    _set_identification_value(sheet, 9, 2, "Geográfica")
    rows = sheet.findall(TABLE + "table-row")
    if len(rows) < 12:
        raise ValueError("Modelo ODS sem linha de vértices.")
    row_model = rows[11]
    row_model.attrib.pop(TABLE + "number-rows-repeated", None)
    insert_at = list(sheet).index(row_model)
    sheet.remove(row_model)
    seen = set()
    for idx, vertex in enumerate(vertices):
        if not isinstance(vertex, dict):
            raise ValueError(f"Vértice {idx + 1}: registro inválido.")
        name = str(vertex.get("sigef_vertex_code") or vertex.get("name") or "").strip()
        if not name or len(name) > 60 or name in seen:
            raise ValueError(f"Vértice {idx + 1}: código ausente/duplicado.")
        seen.add(name)
        lon = _optional_number(vertex.get("longitude"))
        lat = _optional_number(vertex.get("latitude"))
        if lon is None or lat is None or not -75 <= lon <= -30 or not -35 <= lat <= 7:
            raise ValueError(f"Vértice {name}: longitude/latitude inválida.")
        row = deepcopy(row_model)
        cells = _expand_row_cells(row)
        if len(cells) < 12:
            raise ValueError("Modelo ODS sem 12 colunas por vértice.")
        values = [
            name, _decimal_to_dms(lon, "lon"), vertex.get("sigma_lon_m"),
            _decimal_to_dms(lat, "lat"), vertex.get("sigma_lat_m"),
            vertex.get("ellipsoidal_height_m"), vertex.get("sigma_h_m"),
            str(vertex.get("sigef_method") or ""),
            str(vertex.get("boundary_type") or ""),
            str(vertex.get("confrontant_cns") or ""),
            str(vertex.get("confrontant_registration") or ""),
            str(vertex.get("confrontant") or ""),
        ]
        for column, value in enumerate(values):
            if column in (2, 4, 5, 6):
                number = _optional_number(value)
                if number is None:
                    _set_string(cells[column], "")
                else:
                    _set_number(cells[column], number)
            else:
                _set_string(cells[column], str(value or ""))
        sheet.insert(insert_at + idx, row)


def _write_identification_draft(sheet, identity):
    document = "".join(ch for ch in str(identity.get("holder_document") or "") if ch.isdigit())
    values = {
        2: str(identity.get("service_nature") or "Particular"),
        5: "Jurídica" if len(document) == 14 else "Física",
        6: str(identity.get("holder_name") or ""),
        7: document,
        10: str(identity.get("property_name") or ""),
        11: str(identity.get("situation") or ""),
        12: str(identity.get("area_nature") or "Particular"),
        13: str(identity.get("sncr") or ""),
        14: str(identity.get("cns") or ""),
        15: str(identity.get("registration") or ""),
    }
    for row, value in values.items():
        _set_identification_value(sheet, row, 2, value[:255])


def _add_disclaimer_sheet(root):
    spreadsheet = root.find(f".//{OFFICE}spreadsheet")
    if spreadsheet is None:
        raise ValueError("Modelo ODS sem planilha.")
    sheet = ET.Element(TABLE + "table", {TABLE + "name": "AVISO_NAO_SUBMETER"})
    for line in (
        "AMAZONIKA - RASCUNHO INCOMPLETO - NAO SUBMETER AO SIGEF",
        "Este arquivo NAO constitui certificacao, prevalidacao nem planilha apta a protocolo.",
        "Coordenadas e nomes sao transcritos da parcela de trabalho.",
        "Sigma e altura h nao medidos permanecem vazios, nunca recebem zeros ficticios.",
        "Altitude normal HN ou HN interpolada NAO substitui altura elipsoidal h.",
        "Confirmar referencia, epoca, acuracia PS4, limites e confrontantes com o RT.",
        "Revisar e validar no LibreOffice com extensao oficial SIGEF antes de qualquer envio.",
    ):
        row = ET.SubElement(sheet, TABLE + "table-row")
        cell = ET.SubElement(row, TABLE + "table-cell")
        _set_string(cell, line)
    spreadsheet.append(sheet)


def build_working_sigef_ods(payload: dict) -> bytes:
    identity = payload.get("identification") or {}
    parcels = payload.get("parcels") or []
    if not isinstance(identity, dict) or not isinstance(parcels, list) or not 1 <= len(parcels) <= 50:
        raise ValueError("Identificação ou parcelas inválidas (máximo 50).")
    path = _template_path()
    if not path.is_file():
        raise ValueError("Modelo SIGEF ODS não disponível.")
    with ZipFile(path) as original:
        root = ET.fromstring(original.read("content.xml"))
        _write_identification_draft(_sheet(root, "identificacao"), identity)
        first = _sheet(root, "perimetro_1")
        parent = next((part for part in root.iter() if first in list(part)), None)
        if parent is None:
            raise ValueError("Aba perímetro sem vínculo no modelo.")
        original_index = list(parent).index(first)
        template = deepcopy(first)
        for index, parcel in enumerate(parcels):
            if not isinstance(parcel, dict):
                raise ValueError("Parcela inválida.")
            current = first if index == 0 else deepcopy(template)
            if index:
                parent.insert(original_index + index, current)
            current.set(TABLE + "name", f"perimetro_{index + 1}")
            _write_draft_perimeter(current, parcel, index + 1)
        _add_disclaimer_sheet(root)
        content = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        result = BytesIO()
        with ZipFile(result, "w") as target:
            for entry in original.infolist():
                body = content if entry.filename == "content.xml" else original.read(entry.filename)
                info = ZipInfo(entry.filename, date_time=entry.date_time)
                info.comment = entry.comment
                info.extra = entry.extra
                info.internal_attr = entry.internal_attr
                info.external_attr = entry.external_attr
                info.create_system = entry.create_system
                info.compress_type = ZIP_STORED if entry.filename == "mimetype" else ZIP_DEFLATED
                target.writestr(info, body)
    return result.getvalue()
