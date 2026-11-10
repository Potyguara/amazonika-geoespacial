"""Pré-validação conservadora de processamento GNSS Topcon Tools.

Lê relatório nativo HTML/HTM, PDF textual ou tabela XLSX da Amazonika.
NÃO converte pontos de controle em vértices de limite e NÃO atribui
altura elipsoidal, código SIGEF ou confrontação sem validação técnica.
"""
from __future__ import annotations

import io
import math
import re
import unicodedata
from html.parser import HTMLParser

from pyproj import Transformer
from pypdf import PdfReader

MAX_BYTES = 12 * 1024 * 1024
LIMIT_POINTS = 5000


class TopconHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() in ("tr", "p", "div", "h1", "h2", "h3", "br"):
            self.parts.append("\n")
        if tag.lower() in ("td", "th"):
            self.parts.append("\t")
            self.in_cell = True

    def handle_endtag(self, tag):
        if tag.lower() in ("td", "th"):
            self.parts.append("\t")
            self.in_cell = False
        if tag.lower() in ("tr", "p", "div", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)

    def text(self):
        return "".join(self.parts)


def _norm(value: str) -> str:
    result = unicodedata.normalize("NFKD", value)
    return "".join(c for c in result if not unicodedata.combining(c)).casefold().strip()


def _number(value: str) -> float:
    raw = str(value).replace("\u00a0", "").replace(" ", "").strip()
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    result = float(raw)
    if not math.isfinite(result):
        raise ValueError("Valor não finito.")
    return result


def _rows_from_xlsx(raw: bytes) -> str:
    from openpyxl import load_workbook
    workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    lines = []
    try:
        for sheet in workbook:
            lines.append(f"\n{sheet.title}\n")
            for row in sheet.iter_rows(max_row=min(sheet.max_row or 0, 10000),
                                       max_col=min(sheet.max_column or 0, 35),
                                       values_only=True):
                values = [str(cell).strip() if cell is not None else ""
                          for cell in row]
                if any(values):
                    lines.append("\t".join(values))
    finally:
        workbook.close()
    return "\n".join(lines)


def _text(raw: bytes, extension: str) -> str:
    if extension in (".html", ".htm"):
        parser = TopconHTMLParser()
        try:
            decoded = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            decoded = raw.decode("cp1252", errors="replace")
        parser.feed(decoded)
        return parser.text()
    if extension == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(raw), strict=False)
            if len(reader.pages) > 25:
                raise ValueError("Relatório PDF acima de 25 páginas.")
            return "\n".join(page.extract_text(extraction_mode="layout") or ""
                             for page in reader.pages)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("PDF inválido ou sem texto estruturado.") from exc
    if extension == ".xlsx":
        try:
            return _rows_from_xlsx(raw)
        except Exception as exc:
            raise ValueError("Arquivo XLSX inválido.") from exc
    raise ValueError("Formatos aceitos: HTML, HTM, XLSX e PDF textual.")


# Seções por título permitem evitar confundir linhas do quadro de
# coordenadas com vetores, precisão, fator de escala ou controle.
SECTION_KEYS = [
    ("utm", ("coordenadas utm",)),
    ("geo", ("coordenadas geograficas", "coordenadas geodesicas")),
    ("sigma", ("desvio padrao",)),
    ("scale", ("fator de escala",)),
    ("vectors", ("precisao",)),
    ("solution", ("distancia, solucao, orbita e pdop", "distancia solucao orbita e pdop")),
    ("sessions", ("duracao e intervalo",)),
    ("controls", ("pontos de controle",)),
]


def _section(line: str):
    normalized = _norm(line)
    normalized = re.sub(r"\s+", " ", normalized)
    if len(normalized) > 95:
        return None
    for key, names in SECTION_KEYS:
        if normalized in names:
            return key
    return None


def _cells(line: str) -> list[str]:
    # Tabulação é prioritária. HTML do Topcon também usa células separadas
    # por múltiplos espaços.
    cells = [p.strip() for p in re.split(r"\t+| {2,}", line.strip())]
    return [x for x in cells if x]


def _value_after_label(text: str, label: str) -> str | None:
    regex = re.compile(r"(?im)^\s*" + re.escape(label) +
                       r"\s*:\s*([^\n\r]+)")
    found = regex.search(text)
    return found.group(1).strip() if found else None


def _point_name(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{1,32}", value)) and bool(
        re.search(r"[A-Za-z0-9]", value)
    )


def _point_fields(rows: list[list[str]], count: int) -> dict:
    result = {}
    for cells in rows:
        if len(cells) < count + 1 or not _point_name(cells[0]):
            continue
        try:
            nums = [_number(value) for value in cells[1:count + 1]]
        except (ValueError, TypeError):
            continue
        result[cells[0]] = nums
        if len(result) > LIMIT_POINTS:
            raise ValueError("Relatório excede 5.000 pontos.")
    return result


def _geo_coord(text: str, latitude: bool) -> float:
    match = re.fullmatch(
        r"\s*(\d{1,3})[°º]\s*(\d{1,2})['′]\s*"
        r"(\d{1,2}(?:[.,]\d+)?)[\"″]?\s*([NSEWLO])\s*",
        text, re.I
    )
    if not match:
        raise ValueError("Coordenada geográfica inválida: " + text[:50])
    degree, minute, sec = [_number(x) for x in match.groups()[:3]]
    hem = match.group(4).upper()
    if minute >= 60 or sec >= 60:
        raise ValueError("Minutos ou segundos inválidos.")
    if latitude and hem not in ("N", "S"):
        raise ValueError("Hemisfério da latitude inválido.")
    if not latitude and hem not in ("E", "W", "L", "O"):
        raise ValueError("Hemisfério da longitude inválido.")
    value = degree + minute / 60 + sec / 3600
    if value > (90 if latitude else 180):
        raise ValueError("Coordenada geográfica fora de faixa.")
    return -value if hem in ("S", "W", "O") else value


def _parse_geo_rows(rows: list[list[str]]) -> dict:
    points = {}
    for cells in rows:
        if len(cells) < 4 or not _point_name(cells[0]):
            continue
        try:
            lat = _geo_coord(cells[1], latitude=True)
            lon = _geo_coord(cells[2], latitude=False)
            elev = _number(cells[3])
        except ValueError:
            continue
        points[cells[0]] = [lat, lon, elev]
    return points


def _solution_rows(rows: list[list[str]]) -> list[dict]:
    results = []
    for cells in rows:
        if len(cells) < 7 or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}[−–-][A-Za-z0-9_-]{1,32}", cells[0]):
            continue
        try:
            distance = _number(cells[1])
            pdop, hdop, vdop = (_number(cells[-3]), _number(cells[-2]),
                                _number(cells[-1]))
        except (ValueError, TypeError):
            continue
        results.append({
            "baseline": cells[0], "distance_m": distance,
            "solution_type": cells[2], "orbit": cells[3],
            "pdop": pdop, "hdop": hdop, "vdop": vdop,
        })
    return results[:LIMIT_POINTS]


def _sessions(rows: list[list[str]]) -> list[dict]:
    results = []
    for cells in rows:
        if len(cells) < 8 or not _point_name(cells[0]):
            continue
        # Data/hora são mantidas exatamente como constam no arquivo.
        # Não inferir UTC a partir do horário local do receptor.
        if not re.search(r"\d{2}/\d{2}/\d{4}", cells[2]):
            continue
        results.append({
            "point": cells[0], "original_name": cells[1],
            "started_at_reported": cells[2], "ended_at_reported": cells[3],
            "duration": cells[4], "method": cells[5],
            "interval_ms": cells[6], "antenna": cells[7],
        })
    return results[:LIMIT_POINTS]


def parse_topcon_report(raw: bytes, filename: str) -> dict:
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("Relatório vazio ou maior que 12 MB.")
    ext = "." + filename.rsplit(".", 1)[-1].lower()
    text = _text(raw, ext)
    if len(text.strip()) < 120:
        raise ValueError("Não foi possível extrair tabelas do relatório.")
    sections = {key: [] for key, _ in SECTION_KEYS}
    current = None
    for line in text.splitlines():
        marker = _section(line)
        if marker:
            current = marker
            continue
        if current and line.strip():
            sections[current].append(_cells(line))

    utm = _point_fields(sections["utm"], 3)
    geographic = _parse_geo_rows(sections["geo"])
    sigma = _point_fields(sections["sigma"], 4)
    scale = _point_fields(sections["scale"], 1)
    solution = _solution_rows(sections["solution"])
    sessions = _sessions(sections["sessions"])
    if not utm or not geographic:
        raise ValueError(
            "Não foram identificadas as tabelas de coordenadas UTM e geográficas. "
            "Exporte o relatório original do TOPCON com os dois quadros habilitados."
        )

    projection = _value_after_label(text, "Projeção") or ""
    datum = _value_after_label(text, "Datum") or ""
    zone_match = re.search(r"(?:zone[_ -]?|zona\s*)(\d{1,2})", projection, re.I)
    zone = int(zone_match.group(1)) if zone_match else None
    north = "north" in projection.casefold() or "norte" in projection.casefold()
    south = "south" in projection.casefold() or "sul" in projection.casefold()
    if not north and not south and geographic:
        north = next(iter(geographic.values()))[0] >= 0
        south = not north

    errors = []
    warnings = []
    if not re.search(r"sirgas", datum, re.I):
        errors.append("Datum não identificado como SIRGAS: confirmar referencial e época.")
    elif "2000" not in datum:
        warnings.append("TOPCON informa apenas SIRGAS: confirmar SIRGAS 2000 e época das coordenadas antes de gerar SIGEF.")
    if not zone or not 1 <= zone <= 60:
        errors.append("Zona UTM não identificada com segurança.")
    if len(utm) != len(geographic) or set(utm) != set(geographic):
        errors.append("Divergência entre os identificadores UTM e geográficos.")
    points = []
    # Sistemas SIRGAS2000/UTM em uso no Brasil (IBGE):
    # 18N..22N = EPSG 31972..31976; 18S..25S = 31978..31985.
    epsg = None
    if "sirgas" in datum.casefold() and zone:
        if north and 18 <= zone <= 22:
            epsg = 31954 + zone
        elif south and 18 <= zone <= 25:
            epsg = 31960 + zone
    transformer = Transformer.from_crs(
        f"EPSG:{epsg}", "EPSG:4674", always_xy=True,
    ) if epsg else None
    # Para o Brasil, transformar usando diretamente os códigos SIRGAS2000
    # EPSG:31960...31985; em zonas fora da cobertura, bloquear conferência
    # automática em vez de etiquetar outro datum como SIRGAS.
    if transformer is None:
        warnings.append("Conferência cruzada de coordenadas indisponível: CRS/UTM SIRGAS2000 não confirmado.")
    for name, coords in utm.items():
        easting, northing, elevation = coords[1], coords[0], coords[2]
        if not (100000 <= easting <= 900000 and 0 <= northing <= 10000000):
            errors.append(f"{name}: coordenadas UTM fora da faixa esperada.")
        geo = geographic.get(name)
        point = {
            "name": name, "northing_m": northing, "easting_m": easting,
            "elevation_reported_m": elevation,
            "latitude": geo[0] if geo else None,
            "longitude": geo[1] if geo else None,
            "sigma_n_m": sigma[name][0] if name in sigma else None,
            "sigma_e_m": sigma[name][1] if name in sigma else None,
            "sigma_hz_m": sigma[name][2] if name in sigma else None,
            "sigma_u_m": sigma[name][3] if name in sigma else None,
            "scale_combined": scale[name][0] if name in scale else None,
            "point_role": "CONTROL" if name.casefold() in ("base", "estacao base")
                          else "UNCLASSIFIED",
            "sigef_vertex_code": None, "sigef_method": None,
            "ellipsoidal_height_m": None, "vertex_order": None,
        }
        if geo and transformer:
            try:
                lon2, lat2 = transformer.transform(easting, northing)
                delta = max(abs(lon2-geo[1]), abs(lat2-geo[0]))
                point["utm_geographic_delta_deg"] = round(delta, 9)
                if delta > 0.00001:
                    errors.append(f"{name}: UTM e geográfica divergem mais de ~1 m.")
            except Exception:
                warnings.append(f"{name}: transformação UTM não pôde ser conferida.")
        points.append(point)
    if any(p["sigma_hz_m"] is None for p in points if p["point_role"] != "CONTROL"):
        warnings.append("Precisão horizontal faltante em um ou mais pontos.")
    warnings += [
        "Elevação do TOPCON não é assumida como altura elipsoidal: conferir tipo vertical/geóide.",
        "Os pontos não representam automaticamente vértices do perímetro; "
        "classifique limites, ordem e confrontações antes de gerar ODS ou memorial.",
        "A planilha SIGEF final exige identificações e métodos de posicionamento "
        "confirmados pelo responsável técnico.",
    ]
    return {
        "source": "TOPCON_TOOLS", "filename": filename,
        "project": {
            "name": _value_after_label(text, "Nome do Projeto"),
            "created": _value_after_label(text, "Hora da Criação do Projeto"),
            "datum": datum, "projection": projection, "utm_zone": zone,
            "hemisphere": "N" if north else "S",
            "geoid": _value_after_label(text, "Geóide"),
            "adjustment": _value_after_label(text, "Tipo de Ajustamento"),
        },
        "points": points, "point_count": len(points),
        "solution": solution, "sessions": sessions,
        "checks": {"errors": list(dict.fromkeys(errors)),
                   "warnings": list(dict.fromkeys(warnings))},
        "ready_for_sigef": False,
    }
