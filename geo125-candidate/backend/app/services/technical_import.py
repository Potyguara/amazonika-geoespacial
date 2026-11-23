"""Leitura conservadora da planilha oficial SIGEF (.ods).

Não inventa nomes, cotas, confrontantes nem identificadores faltantes.
Os campos são associados ao vértice inicial de cada segmento.
"""
from __future__ import annotations

import io
import math
import re
import unicodedata
import zipfile
from xml.etree import ElementTree as ET

from fastapi import HTTPException

TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"

VERTEX_RE = re.compile(r"^[A-Z0-9]{2,12}-(?:M|P|V)-[A-Z0-9]+$", re.I)
DMS_RE = re.compile(
    r"^\s*(\d{1,3})[\s°]+(\d{1,2})[\s'′]+(\d{1,2}(?:[.,]\d+)?)"
    r"\s*(?:[\"″])?\s*([NSEWLO])\s*$", re.I
)


def _cell_text(cell: ET.Element) -> str:
    paragraphs = []
    for para in cell.iter(TEXT + "p"):
        paragraphs.append("".join(para.itertext()).strip())
    result = " ".join(p for p in paragraphs if p).strip()
    if not result:
        result = (cell.get(OFFICE + "value") or "").strip()
    return result


def _rows(table: ET.Element):
    for row in table.findall(TABLE + "table-row"):
        count = int(row.get(TABLE + "number-rows-repeated", "1"))
        if count > 1000 and not list(row.iter(TEXT + "p")):
            continue
        values = []
        for cell in row:
            if cell.tag not in {TABLE + "table-cell", TABLE + "covered-table-cell"}:
                continue
            repeat = int(cell.get(TABLE + "number-columns-repeated", "1"))
            if repeat < 1 or repeat > 100000:
                raise ValueError("Planilha com repetições de células inválidas.")
            values.extend([_cell_text(cell)] * min(repeat, max(0, 30 - len(values))))
            if len(values) >= 30:
                break
        for _ in range(min(count, 1000)):
            yield values


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.lower())
    return "".join(ch for ch in value if not unicodedata.combining(ch)).strip()


def _decimal(value: str) -> float | None:
    value = value.strip()
    if not value:
        return None
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    try:
        result = float(value)
    except ValueError as exc:
        raise ValueError(f"Valor numérico inválido: {value[:35]}") from exc
    if not math.isfinite(result):
        raise ValueError("Coordenada, altitude ou precisão não finita.")
    return result


def _dms(value: str, latitude: bool) -> float:
    match = DMS_RE.match(value)
    if match:
        degree, minute, second = (float(x.replace(",", ".")) for x in match.groups()[:3])
        hemisphere = match.group(4).upper()
        if minute >= 60 or second >= 60:
            raise ValueError(f"Minutos/segundos inválidos: {value}")
        coordinate = degree + minute / 60 + second / 3600
        if hemisphere in {"S", "W", "O"}:
            coordinate = -coordinate
    else:
        parsed = _decimal(value.replace("°", ""))
        if parsed is None:
            raise ValueError("Coordenada geográfica ausente.")
        coordinate = parsed
    if abs(coordinate) > (90 if latitude else 180):
        raise ValueError(f"Coordenada fora dos limites: {value}")
    return round(coordinate, 11)


def _field(rows: list[list[str]], names: set[str]) -> str:
    for row in rows:
        if not row:
            continue
        label = _normalize(row[0]).rstrip(":")
        if label in names:
            return (row[1] if len(row) > 1 else "").strip()
    return ""


def parse_sigef_ods(raw: bytes) -> dict:
    if not raw or len(raw) > 15 * 1024 * 1024:
        raise ValueError("Planilha ODS vazia ou maior que 15 MB.")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            if len(names) > 1500 or "content.xml" not in names:
                raise ValueError("ODS inválido ou com arquivos internos excessivos.")
            info = archive.getinfo("content.xml")
            if info.file_size > 20 * 1024 * 1024:
                raise ValueError("Planilha excede o limite de conteúdo XML.")
            root = ET.fromstring(archive.read("content.xml"))
    except (zipfile.BadZipFile, ET.ParseError, KeyError) as exc:
        raise ValueError("Arquivo não é uma planilha ODS válida.") from exc

    sheets = {
        name.lower(): list(_rows(table))
        for table in root.iter(TABLE + "table")
        if (name := table.get(TABLE + "name", "")).lower() == "identificacao"
        or name.lower().startswith("perimetro_")
    }
    identification = sheets.get("identificacao")
    perimeters = [(name, rows) for name, rows in sheets.items() if name.startswith("perimetro_")]
    if not identification or not perimeters:
        raise ValueError("Planilha SIGEF deve conter as abas 'identificacao' e 'perimetro_1'.")

    owner = _field(identification, {"nome"})
    cpf = _field(identification, {"cpf", "cnpj"})
    title = _field(identification, {"denominacao"})
    municipality = ""
    for index, row in enumerate(identification):
        if row and _normalize(row[0]).startswith("municipio"):
            for below in identification[index + 1:index + 5]:
                if below and below[0].strip():
                    municipality = below[0].strip()
                    break
            break

    metadata = {
        "source": "SIGEF_ODS",
        "owner": owner,
        "person_type": _field(identification, {"tipo pessoa"}),
        "cpf_cnpj": cpf,
        "name": title,
        "service_nature": _field(identification, {"natureza do servico"}),
        "legal_status": _field(identification, {"situacao"}),
        "area_nature": _field(identification, {"natureza da area"}),
        "sncr": _field(identification, {"codigo do imovel(sncr/incra)", "codigo do imovel (sncr/incra)"}),
        "cns": _field(identification, {"codigo do cartorio (cns)"}),
        "registration": _field(identification, {"matricula"}),
        "municipality": municipality,
        "reference_system": "SIRGAS 2000",
    }
    features: list[dict] = []
    total_vertices = 0
    for name, rows in sorted(perimeters):
        header = next((i for i, row in enumerate(rows)
                       if row and _normalize(row[0]) in {"vertice", "vertices"}), None)
        if header is None:
            raise ValueError(f"Tabela de vértices não localizada na aba {name}.")
        coordinate_type = ""
        for row in rows[:header]:
            if row and _normalize(row[0]).startswith("tipo de coordenada"):
                coordinate_type = row[1].strip() if len(row) > 1 else ""
        if "geograf" not in _normalize(coordinate_type):
            raise ValueError(f"A aba {name} não usa coordenadas geográficas; conversão UTM requer zona explícita.")
        records = []
        for row in rows[header + 1:]:
            if not row or not VERTEX_RE.fullmatch(row[0].strip()):
                continue
            row = (row + [""] * 12)[:12]
            lon = _dms(row[1], latitude=False)
            lat = _dms(row[3], latitude=True)
            records.append({
                "name": row[0].strip(), "longitude": lon, "latitude": lat,
                "longitude_original": row[1], "latitude_original": row[3],
                "sigma_lon_m": _decimal(row[2]), "sigma_lat_m": _decimal(row[4]),
                "altitude_m": _decimal(row[5]), "sigma_altitude_m": _decimal(row[6]),
                "positioning_method": row[7], "boundary_type": row[8],
                "confrontant_cns": row[9], "confrontant_registration": row[10],
                "confrontant": row[11],
            })
        if len(records) < 3:
            raise ValueError(f"A aba {name} não contém ao menos três vértices válidos.")
        if len(records) > 50000:
            raise ValueError("Número de vértices acima do limite permitido.")
        coords = [[record["longitude"], record["latitude"]] for record in records]
        if coords[0] == coords[-1]:
            records.pop()
            coords.pop()
        if len({tuple(point) for point in coords}) < 3:
            raise ValueError(f"O perímetro {name} não possui três vértices distintos.")
        coords.append(coords[0])
        total_vertices += len(records)
        if total_vertices > 100000:
            raise ValueError("Número total de vértices excedido.")
        perimeter_title = _field(rows[:header], {"denominacao"}) or title or name
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {
                "workPolygonName": perimeter_title,
                "vertexNames": [record["name"] for record in records],
                "confrontants": [record["confrontant"] for record in records],
                "altitudes": [("" if record["altitude_m"] is None else str(record["altitude_m"])) for record in records],
                "sigef_vertex_details": records,
                "sigef_parcel_number": _field(rows[:header], {"parcela numero"}),
                "sigef_side": _field(rows[:header], {"lado"}),
                "sigef_metadata": metadata,
            },
        })
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": metadata,
        "warnings": [
            "Confira área, azimutes, confrontantes e datum antes de emitir documentos.",
            "Confrontante de cada linha é interpretado como referente ao segmento que parte do vértice.",
        ],
        "vertex_count": total_vertices,
    }
