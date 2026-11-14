"""Exportação preliminar de ODS SIGEF a partir de vértices confirmados.

Preserva a estrutura e os estilos do modelo ODS instalado. A certificação
oficial e a análise de conflitos permanecem sob responsabilidade do SIGEF.
"""
from __future__ import annotations

import io
import math
from copy import deepcopy
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZipInfo, ZIP_STORED, ZIP_DEFLATED

from shapely.geometry import shape

from app.services.sigef_ods import (
    TABLE, _template_path, _sheet, _expand_row_cells, _set_identification_value,
    _set_number, _set_string, _decimal_to_dms,
)
from app.services.sigef_parcel_review import review_sigef_parcels
from app.services.topcon_perimeter_review import review_topcon_perimeter


def _required_text(value, field: str) -> str:
    value = str(value or "").strip()
    if not value:
        raise ValueError(f"Preenchimento obrigatório: {field}.")
    if len(value) > 500:
        raise ValueError(f"Campo excessivamente longo: {field}.")
    return value


def _required_number(value, field: str, *, nonnegative: bool = True, strictly_positive: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field}: valor numérico inválido.")
    try:
        number = float(str(value).strip().replace(",", "."))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{field}: número ausente ou inválido.") from exc
    if not math.isfinite(number) or (nonnegative and number < 0) or (strictly_positive and number <= 0):
        raise ValueError(f"{field}: precisão/altura inválida.")
    return number


def _write_identification(sheet, identity: dict) -> None:
    doc = "".join(c for c in str(identity.get("holder_document") or "") if c.isdigit())
    kind = "Jurídica" if len(doc) == 14 else "Física"
    values = {
        2: str(identity.get("service_nature") or "Particular"),
        5: kind,
        6: _required_text(identity.get("holder_name"), "titular"),
        7: doc,
        10: _required_text(identity.get("property_name"), "denominação"),
        11: _required_text(identity.get("situation"), "situação"),
        12: str(identity.get("area_nature") or "Particular"),
        13: str(identity.get("sncr") or ""),
        14: str(identity.get("cns") or ""),
        15: str(identity.get("registration") or ""),
    }
    for row_number, value in values.items():
        _set_identification_value(sheet, row_number, 2, value)
    rows = sheet.findall(TABLE + "table-row")
    if len(rows) < 17:
        raise ValueError("Modelo SIGEF sem linha de municípios.")
    row = rows[16]
    cells = _expand_row_cells(row)
    municipalities = identity.get("municipalities") or []
    while len(cells) < len(municipalities):
        fresh = deepcopy(cells[-1])
        row.append(fresh)
        cells.append(fresh)
    for index, cell in enumerate(cells):
        _set_string(cell, municipalities[index] if index < len(municipalities) else "")


def _write_perimeter(sheet, parcel: dict) -> None:
    vertices = parcel["vertices"]
    if len(vertices) < 3 or len(vertices) > 5000:
        raise ValueError("Perímetro exige de 3 a 5000 vértices.")
    # A geometria e a ordem são derivadas somente destes mesmos vértices.
    checked = review_topcon_perimeter(vertices)
    if not checked["ready_for_ods"]:
        raise ValueError("Perímetro: " + "; ".join(checked["errors"][:5]))
    sheet.set(TABLE + "name", str(parcel["_sheet_name"]))
    _set_identification_value(sheet, 3, 2, _required_text(parcel["name"], "parcela"))
    _set_identification_value(sheet, 4, 2, str(parcel["number"]))
    _set_identification_value(sheet, 9, 2, "Geográfica")
    rows = sheet.findall(TABLE + "table-row")
    if len(rows) < 12:
        raise ValueError("Modelo SIGEF sem linha de dados.")
    template_row = rows[11]
    template_index = list(sheet).index(template_row)
    sheet.remove(template_row)
    for index, vertex in enumerate(vertices):
        row = deepcopy(template_row)
        cells = _expand_row_cells(row)
        if len(cells) < 12:
            raise ValueError("Modelo SIGEF exige 12 colunas por vértice.")
        name = _required_text(vertex.get("sigef_vertex_code"), "código do vértice")
        longitude = float(vertex["longitude"])
        latitude = float(vertex["latitude"])
        # Sigma horizontal única não substitui incertezas individuais por eixo.
        sigma_lon = _required_number(vertex.get("sigma_lon_m"), "sigma longitude", strictly_positive=True)
        sigma_lat = _required_number(vertex.get("sigma_lat_m"), "sigma latitude", strictly_positive=True)
        height = _required_number(vertex.get("ellipsoidal_height_m"), "altura elipsoidal", nonnegative=False)
        sigma_h = _required_number(vertex.get("sigma_h_m"), "sigma altura", strictly_positive=True)
        values = [
            name,
            _decimal_to_dms(longitude, "lon"),
            sigma_lon,
            _decimal_to_dms(latitude, "lat"),
            sigma_lat,
            height,
            sigma_h,
            _required_text(vertex.get("sigef_method"), "método"),
            _required_text(vertex.get("boundary_type"), "tipo de limite"),
            str(vertex.get("confrontant_cns") or ""),
            str(vertex.get("confrontant_registration") or ""),
            _required_text(vertex.get("confrontant"), "confrontante"),
        ]
        for col, value in enumerate(values):
            if col in (2, 4, 5, 6):
                _set_number(cells[col], value)
            else:
                _set_string(cells[col], value)
        sheet.insert(template_index + index, row)


def build_reviewed_sigef_ods(payload: dict) -> bytes:
    """Exportação estruturada, sem validar certificação nem obter dados faltantes."""
    identity = payload.get("identification") or {}
    parcels = payload.get("parcels") or []
    if not isinstance(identity, dict) or not isinstance(parcels, list):
        raise ValueError("Identificação ou parcelas inválidas.")
    if not 1 <= len(parcels) <= 50:
        raise ValueError("Informe de 1 a 50 parcelas.")
    validated_parcels = []
    for index, parcel in enumerate(parcels, 1):
        if not isinstance(parcel, dict):
            raise ValueError(f"Parcela {index}: dados inválidos.")
        vertices = parcel.get("vertices") or []
        checked = review_topcon_perimeter(vertices)
        if not checked["ready_for_ods"]:
            raise ValueError(f"Parcela {index}: " + "; ".join(checked["errors"][:5]))
        # Furo/encravada demanda modelo específico com anéis e associação correta.
        if len(shape(checked["geometry"]).interiors):
            raise ValueError("Perímetros encravados requerem integração específica.")
        validated_parcels.append({
            **parcel,
            "number": str(parcel.get("number") or index),
            "name": _required_text(parcel.get("name"), f"parcela {index}"),
            "geometry": checked["geometry"],
            "_sheet_name": f"perimetro_{index}",
        })
    check = review_sigef_parcels({
        "identification": identity,
        "parcels": validated_parcels,
        "neighbors": payload.get("neighbors") or [],
    })
    if check["errors"]:
        raise ValueError("Pré-validação SIGEF: " + "; ".join(check["errors"][:8]))

    template = _template_path()
    if not template.is_file():
        raise ValueError("Modelo ODS SIGEF não disponível no backend.")
    with ZipFile(template) as source:
        root = ET.fromstring(source.read("content.xml"))
        _write_identification(_sheet(root, "identificacao"), identity)
        first = _sheet(root, "perimetro_1")
        parent = next((p for p in root.iter() if first in list(p)), None)
        if parent is None:
            raise ValueError("Perímetro do modelo não está vinculado à planilha.")
        index = list(parent).index(first)
        pristine = deepcopy(first)
        for pos, parcel in enumerate(validated_parcels):
            current = first if pos == 0 else deepcopy(pristine)
            # Clone antes de alterar o modelo original para preservar o layout.
            if pos > 0:
                parent.insert(index + pos, current)
            _write_perimeter(current, parcel)
        data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        result = io.BytesIO()
        with ZipFile(result, "w") as target:
            for entry in source.infolist():
                content = data if entry.filename == "content.xml" else source.read(entry.filename)
                info = ZipInfo(entry.filename, date_time=entry.date_time)
                info.comment = entry.comment
                info.extra = entry.extra
                info.internal_attr = entry.internal_attr
                info.external_attr = entry.external_attr
                info.create_system = entry.create_system
                info.compress_type = ZIP_STORED if entry.filename == "mimetype" else ZIP_DEFLATED
                target.writestr(info, content)
    return result.getvalue()
