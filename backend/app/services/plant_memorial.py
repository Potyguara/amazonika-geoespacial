from __future__ import annotations

import json
import math
import textwrap
from io import BytesIO
from pathlib import Path
from typing import Any

from pyproj import CRS, Transformer
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.core.config import get_settings


DEFAULT_DOCUMENT_TEMPLATE: dict[str, Any] = {
    "company_name": "Amazonika Engenharia",
    "cnpj": "49.158.834/0001-19",
    "address": "Av. Almirante Barroso, 620-B, Centro, Macapá/AP.",
    "email": "amazonika@amazonikaengenharia.com.br",
    "responsible_name": "",
    "responsible_registration": "",
    "document_footer": "Documento técnico gerado pelo Amazônika Geoespacial.",
    "logo_path": "app/assets/amazonika-logo.png",
}


def _config_path() -> Path:
    path = get_settings().storage_dir / "document_template"
    path.mkdir(parents=True, exist_ok=True)
    return path / "config.json"


def load_document_template() -> dict[str, Any]:
    result = dict(DEFAULT_DOCUMENT_TEMPLATE)
    path = _config_path()
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                result.update({key: value for key, value in payload.items() if value is not None})
        except Exception:
            pass
    return result


def save_document_template(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "company_name",
        "cnpj",
        "address",
        "email",
        "responsible_name",
        "responsible_registration",
        "document_footer",
        "logo_path",
    }
    current = load_document_template()
    for key, value in payload.items():
        if key in allowed and isinstance(value, str):
            current[key] = value.strip()
    _config_path().write_text(
        json.dumps(current, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return current


def save_document_logo(content: bytes, suffix: str) -> str:
    if suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        raise ValueError("Use logomarca PNG ou JPG.")
    directory = _config_path().parent
    for old in directory.glob("logo.*"):
        old.unlink(missing_ok=True)
    target = directory / f"logo{suffix.lower()}"
    target.write_bytes(content)
    current = load_document_template()
    current["logo_path"] = str(target)
    save_document_template(current)
    return str(target)


def _logo_path(config: dict[str, Any]) -> Path | None:
    candidate = Path(str(config.get("logo_path") or ""))
    if candidate.is_absolute() and candidate.exists():
        return candidate
    project_candidate = Path("/app") / candidate
    if project_candidate.exists():
        return project_candidate
    local_candidate = Path(__file__).resolve().parents[2] / candidate
    if local_candidate.exists():
        return local_candidate
    return None


def _project_vertices(vertices: list[dict[str, Any]]) -> tuple[list[tuple[float, float]], str]:
    centroid_lon = sum(float(item["longitude"]) for item in vertices) / len(vertices)
    centroid_lat = sum(float(item["latitude"]) for item in vertices) / len(vertices)
    zone = max(1, min(60, int((centroid_lon + 180) / 6) + 1))
    south = centroid_lat < 0
    proj = f"+proj=utm +zone={zone} {'+south' if south else ''} +ellps=GRS80 +units=m +no_defs"
    transformer = Transformer.from_crs("EPSG:4674", CRS.from_proj4(proj), always_xy=True)
    projected = [
        transformer.transform(float(item["longitude"]), float(item["latitude"]))
        for item in vertices
    ]
    return projected, f"SIRGAS 2000 / UTM fuso {zone}{'S' if south else 'N'}"


def _nice_scale(distance: float) -> float:
    if distance <= 0:
        return 1.0
    exponent = 10 ** math.floor(math.log10(distance))
    normalized = distance / exponent
    if normalized >= 5:
        return 5 * exponent
    if normalized >= 2:
        return 2 * exponent
    return exponent


def build_plant_memorial_pdf(
    *,
    title: str,
    owner_name: str | None,
    responsible_name: str | None,
    area_hectares: float,
    perimeter_meters: float,
    vertices: list[dict[str, Any]],
    memorial_text: str,
) -> bytes:
    config = load_document_template()
    responsible = responsible_name or config.get("responsible_name") or "Não informado"
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)

    # Cabeçalho
    logo = _logo_path(config)
    if logo:
        try:
            pdf.drawImage(ImageReader(str(logo)), 28, height - 76, width=70, height=46, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass

    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawString(110, height - 40, str(config.get("company_name") or "Amazonika Engenharia"))
    pdf.setFont("Helvetica", 8.5)
    pdf.drawString(110, height - 54, f"CNPJ: {config.get('cnpj') or '—'}")
    pdf.drawString(110, height - 66, f"{config.get('address') or ''}  •  {config.get('email') or ''}")

    pdf.setStrokeColorRGB(0.09, 0.30, 0.23)
    pdf.setLineWidth(2)
    pdf.line(28, height - 84, width - 28, height - 84)

    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawCentredString(width / 2, height - 112, "PLANTA GEORREFERENCIADA")
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawCentredString(width / 2, height - 130, title)

    pdf.setFont("Helvetica", 8.5)
    pdf.drawString(35, height - 151, f"Detentor/Interessado: {owner_name or 'Não informado'}")
    pdf.drawString(35, height - 164, f"Responsável técnico: {responsible}")
    pdf.drawRightString(width - 35, height - 151, f"Área: {area_hectares:,.4f} ha")
    pdf.drawRightString(width - 35, height - 164, f"Perímetro: {perimeter_meters:,.3f} m")

    projected, crs_label = _project_vertices(vertices)
    xs = [point[0] for point in projected]
    ys = [point[1] for point in projected]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)

    map_left, map_bottom = 48.0, 205.0
    map_width, map_height = width - 96.0, height - 390.0
    factor = min(map_width / span_x, map_height / span_y) * 0.86
    used_w, used_h = span_x * factor, span_y * factor
    offset_x = map_left + (map_width - used_w) / 2
    offset_y = map_bottom + (map_height - used_h) / 2

    def xy(point: tuple[float, float]) -> tuple[float, float]:
        return (
            offset_x + (point[0] - min_x) * factor,
            offset_y + (point[1] - min_y) * factor,
        )

    path = pdf.beginPath()
    first_x, first_y = xy(projected[0])
    path.moveTo(first_x, first_y)
    for point in projected[1:]:
        px, py = xy(point)
        path.lineTo(px, py)
    path.close()
    pdf.setFillColorRGB(0.75, 0.88, 0.79)
    pdf.setStrokeColorRGB(0.05, 0.42, 0.28)
    pdf.setLineWidth(2.2)
    pdf.drawPath(path, fill=1, stroke=1)

    pdf.setFont("Helvetica-Bold", 7)
    for vertex, point in zip(vertices, projected):
        px, py = xy(point)
        pdf.setFillColorRGB(0.95, 0.50, 0.08)
        pdf.circle(px, py, 2.7, fill=1, stroke=0)
        pdf.setFillColorRGB(0.08, 0.22, 0.17)
        pdf.drawString(px + 4, py + 3, str(vertex["name"]))

    # Norte
    north_x, north_y = width - 66, map_bottom + map_height - 10
    pdf.setStrokeColorRGB(0.08, 0.22, 0.17)
    pdf.setLineWidth(1.5)
    pdf.line(north_x, north_y - 28, north_x, north_y)
    pdf.line(north_x, north_y, north_x - 5, north_y - 9)
    pdf.line(north_x, north_y, north_x + 5, north_y - 9)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(north_x, north_y + 4, "N")

    # Barra de escala baseada no sistema projetado.
    scale_m = _nice_scale(span_x / 4)
    scale_points = scale_m * factor
    scale_x, scale_y = 55, 190
    pdf.setLineWidth(3)
    pdf.line(scale_x, scale_y, scale_x + scale_points, scale_y)
    pdf.setFont("Helvetica", 7.5)
    pdf.drawString(scale_x, scale_y - 12, "0")
    pdf.drawRightString(scale_x + scale_points, scale_y - 12, f"{scale_m:g} m")

    pdf.setFont("Helvetica", 7.5)
    pdf.drawRightString(width - 35, 190, crs_label)

    # Tabela resumida de vértices
    table_y = 155
    pdf.setFillColorRGB(0.93, 0.96, 0.94)
    pdf.rect(32, table_y, width - 64, 20, fill=1, stroke=0)
    pdf.setFillColorRGB(0.08, 0.22, 0.17)
    pdf.setFont("Helvetica-Bold", 7)
    headers = ["Vértice", "Latitude", "Longitude", "Próximo", "Azimute", "Distância"]
    positions = [40, 95, 245, 405, 470, 560]
    for header, pos in zip(headers, positions):
        pdf.drawString(pos, table_y + 7, header)

    pdf.setFont("Helvetica", 6.5)
    row_y = table_y - 11
    for vertex in vertices[:8]:
        values = [
            vertex["name"],
            vertex["latitude_dms"],
            vertex["longitude_dms"],
            vertex["next_vertex"],
            f"{vertex['azimuth_degrees']:.6f}°",
            f"{vertex['distance_meters']:.3f} m",
        ]
        for value, pos in zip(values, positions):
            pdf.drawString(pos, row_y, str(value)[:34])
        row_y -= 10
    if len(vertices) > 8:
        pdf.setFont("Helvetica-Oblique", 6.5)
        pdf.drawString(40, row_y, f"+ {len(vertices) - 8} vértices listados integralmente no memorial.")

    pdf.setFont("Helvetica", 7)
    pdf.drawCentredString(width / 2, 24, str(config.get("document_footer") or ""))

    # Memorial
    pdf.showPage()
    pdf.setPageSize(A4)
    width, height = A4
    if logo:
        try:
            pdf.drawImage(ImageReader(str(logo)), 34, height - 72, width=60, height=38, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(105, height - 42, "MEMORIAL DESCRITIVO")
    pdf.setFont("Helvetica", 8)
    pdf.drawString(105, height - 56, title)
    pdf.line(34, height - 82, width - 34, height - 82)

    y = height - 108
    pdf.setFont("Helvetica", 9)
    for paragraph in memorial_text.splitlines():
        if not paragraph.strip():
            y -= 8
            continue
        for line in textwrap.wrap(paragraph, width=104, break_long_words=False):
            if y < 58:
                pdf.showPage()
                pdf.setPageSize(A4)
                y = height - 52
                pdf.setFont("Helvetica", 9)
            pdf.drawString(42, y, line)
            y -= 12
        y -= 2

    pdf.setFont("Helvetica", 7)
    pdf.drawCentredString(width / 2, 28, str(config.get("document_footer") or ""))
    pdf.save()
    return buffer.getvalue()
