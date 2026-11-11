from __future__ import annotations

import hashlib
import io
import json
import math
import secrets
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import qrcode
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.analysis import Analysis, AnalysisResult
from app.models.auth import User
from app.models.catalog import Source, SourceVersion
from app.models.report import ReportEmission


LOCAL_TZ = ZoneInfo("America/Belem")

PALETTE = [
    "#d94841",
    "#e08a24",
    "#3f71c1",
    "#8a52b8",
    "#00897b",
    "#a15c38",
    "#c13f78",
    "#556b2f",
]


def _local_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(LOCAL_TZ)


def _fmt_datetime(value: datetime | None) -> str:
    local = _local_datetime(value)
    return local.strftime("%d/%m/%Y %H:%M:%S") if local else "—"


def _fmt_number(value: float | int | None, decimals: int = 4) -> str:
    if value is None:
        return "—"

    raw = f"{float(value):,.{decimals}f}"
    return raw.replace(",", "#").replace(".", ",").replace("#", ".")


def _font(size: int, bold: bool = False):
    path = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    )
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _geometry_coordinates(geometry: dict):
    geom_type = geometry.get("type")
    coordinates = geometry.get("coordinates") or []

    if geom_type == "GeometryCollection":
        points = []
        for item in geometry.get("geometries") or []:
            points.extend(_geometry_coordinates(item))
        return points

    if geom_type == "Point":
        return [coordinates] if coordinates else []

    if geom_type == "MultiPoint":
        return list(coordinates)

    if geom_type == "LineString":
        return list(coordinates)

    if geom_type == "MultiLineString":
        return [
            point
            for line in coordinates
            for point in line
        ]

    if geom_type == "Polygon":
        return [
            point
            for ring in coordinates
            for point in ring
        ]

    if geom_type == "MultiPolygon":
        return [
            point
            for polygon in coordinates
            for ring in polygon
            for point in ring
        ]

    return []

def _bbox(geometries: list[dict]) -> tuple[float, float, float, float]:
    points = [
        point
        for geometry in geometries
        for point in _geometry_coordinates(geometry)
        if len(point) >= 2
    ]

    if not points:
        return (-52.0, 0.0, -51.0, 1.0)

    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]

    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)

    dx = maxx - minx
    dy = maxy - miny

    if dx < 0.0005:
        dx = 0.002
        minx -= dx / 2
        maxx += dx / 2

    if dy < 0.0005:
        dy = 0.002
        miny -= dy / 2
        maxy += dy / 2

    pad_x = max(dx * 0.12, 0.0002)
    pad_y = max(dy * 0.12, 0.0002)

    return (
        minx - pad_x,
        miny - pad_y,
        maxx + pad_x,
        maxy + pad_y,
    )


def _projector(
    bbox: tuple[float, float, float, float],
    left: int,
    top: int,
    right: int,
    bottom: int,
):
    minx, miny, maxx, maxy = bbox

    width = max(right - left, 1)
    height = max(bottom - top, 1)

    scale_x = width / max(maxx - minx, 1e-12)
    scale_y = height / max(maxy - miny, 1e-12)
    scale = min(scale_x, scale_y)

    render_width = (maxx - minx) * scale
    render_height = (maxy - miny) * scale

    offset_x = left + (width - render_width) / 2
    offset_y = top + (height - render_height) / 2

    def project(point):
        lon = float(point[0])
        lat = float(point[1])

        x = offset_x + (lon - minx) * scale
        y = offset_y + render_height - (lat - miny) * scale

        return (round(x), round(y))

    return project


def _draw_geometry(
    draw: ImageDraw.ImageDraw,
    geometry: dict,
    project,
    *,
    outline: str,
    fill: str | None = None,
    width: int = 4,
):
    geom_type = geometry.get("type")
    coordinates = geometry.get("coordinates") or []

    if geom_type == "Point":
        x, y = project(coordinates)
        r = 8
        draw.ellipse(
            (x - r, y - r, x + r, y + r),
            fill=fill or outline,
            outline="#ffffff",
            width=2,
        )
        return

    if geom_type == "Polygon":
        polygons = [coordinates]
    elif geom_type == "MultiPolygon":
        polygons = coordinates
    else:
        return

    for polygon in polygons:
        if not polygon:
            continue

        exterior = [project(point) for point in polygon[0]]

        if len(exterior) >= 3:
            if fill:
                draw.polygon(exterior, fill=fill)
            draw.line(exterior + [exterior[0]], fill=outline, width=width)

        for hole in polygon[1:]:
            ring = [project(point) for point in hole]
            if len(ring) >= 3:
                draw.polygon(ring, fill="#ffffff")
                draw.line(ring + [ring[0]], fill=outline, width=max(1, width - 1))


def _nice_scale(meters: float) -> float:
    if meters <= 0:
        return 1

    magnitude = 10 ** math.floor(math.log10(meters))
    normalized = meters / magnitude

    if normalized < 2:
        nice = 1
    elif normalized < 5:
        nice = 2
    else:
        nice = 5

    return nice * magnitude


def _map_scale_meters(
    bbox: tuple[float, float, float, float],
    map_width_px: int,
) -> tuple[float, int]:
    minx, miny, maxx, maxy = bbox
    center_lat = (miny + maxy) / 2

    width_degrees = maxx - minx
    width_meters = (
        width_degrees
        * 111_320
        * max(math.cos(math.radians(center_lat)), 0.05)
    )

    target_meters = width_meters * 0.20
    scale_meters = _nice_scale(target_meters)

    pixels = int(
        (scale_meters / max(width_meters, 1))
        * map_width_px
    )

    return scale_meters, max(pixels, 30)


def _subject_geojson(db: Session, analysis_id: UUID) -> dict:
    raw = db.execute(
        text(
            """
            SELECT ST_AsGeoJSON(ST_Force2D(input_geom))
            FROM analyses
            WHERE id = :analysis_id
            """
        ),
        {"analysis_id": analysis_id},
    ).scalar_one_or_none()

    if not raw:
        raise ValueError("Geometria da análise não encontrada.")

    return json.loads(raw)


def _context_buffer_m(area_hectares: float | None) -> int:
    """Distância de contexto cartográfico ao redor da geometria analisada."""
    if area_hectares is None:
        return 1000

    area = float(area_hectares)

    if area < 50:
        return 1000

    if area <= 500:
        return 2000

    return 5000


def _context_extent_geojson(
    db: Session,
    analysis_id: UUID,
    buffer_m: int,
) -> dict:
    raw = db.execute(
        text(
            """
            SELECT ST_AsGeoJSON(
                ST_Envelope(
                    ST_Buffer(
                        ST_Force2D(input_geom)::geography,
                        :buffer_m
                    )::geometry
                )
            )
            FROM analyses
            WHERE id = :analysis_id
            """
        ),
        {
            "analysis_id": analysis_id,
            "buffer_m": buffer_m,
        },
    ).scalar_one_or_none()

    if not raw:
        return _subject_geojson(db, analysis_id)

    return json.loads(raw)


def _context_geojson(
    db: Session,
    analysis_id: UUID,
    version_id: UUID,
    buffer_m: int,
    limit: int = 250,
) -> tuple[dict | None, int]:
    """
    Obtém feições da base existentes no entorno da área analisada.

    Diferentemente de _overlap_geojson(), este método não recorta
    somente a interseção com o imóvel. Ele preserva o contexto espacial
    dentro do buffer utilizado no mapa documental.
    """
    row = db.execute(
        text(
            """
            WITH area_contexto AS (
                SELECT
                    ST_Buffer(
                        ST_Force2D(input_geom)::geography,
                        :buffer_m
                    )::geometry AS geom
                FROM analyses
                WHERE id = :analysis_id
            ),
            candidatas AS (
                SELECT ST_Force2D(g.geom) AS geom
                FROM geo_features g
                CROSS JOIN area_contexto a
                WHERE g.version_id = :version_id
                  AND g.geom IS NOT NULL
                  AND g.geom && a.geom
                  AND ST_Intersects(g.geom, a.geom)
                LIMIT :feature_limit
            )
            SELECT
                COUNT(*) AS feature_count,
                ST_AsGeoJSON(
                    ST_Collect(
                        ST_Intersection(
                            c.geom,
                            a.geom
                        )
                    )
                ) AS geometry
            FROM candidatas c
            CROSS JOIN area_contexto a
            """
        ),
        {
            "analysis_id": analysis_id,
            "version_id": version_id,
            "buffer_m": buffer_m,
            "feature_limit": limit,
        },
    ).mappings().first()

    if not row:
        return None, 0

    count = int(row["feature_count"] or 0)
    raw = row["geometry"]

    if not raw:
        return None, count

    try:
        return json.loads(raw), count
    except Exception:
        return None, count


def _overlap_geojson(
    db: Session,
    analysis_id: UUID,
    version_id: UUID,
) -> dict | None:
    raw = db.execute(
        text(
            """
            SELECT ST_AsGeoJSON(
                ST_UnaryUnion(
                    ST_Collect(
                        ST_Intersection(
                            ST_Force2D(g.geom),
                            ST_Force2D(a.input_geom)
                        )
                    )
                )
            )
            FROM geo_features g
            CROSS JOIN analyses a
            WHERE a.id = :analysis_id
              AND g.version_id = :version_id
              AND g.geom IS NOT NULL
              AND ST_Intersects(g.geom, a.input_geom)
            """
        ),
        {
            "analysis_id": analysis_id,
            "version_id": version_id,
        },
    ).scalar_one_or_none()

    if not raw:
        return None

    try:
        return json.loads(raw)
    except Exception:
        return None


def _analysis_metrics(
    db: Session,
    analysis_id: UUID,
) -> dict:
    row = db.execute(
        text(
            """
            SELECT
                CASE
                    WHEN GeometryType(input_geom) IN ('POLYGON','MULTIPOLYGON')
                    THEN ST_Perimeter(
                        ST_Force2D(input_geom)::geography
                    )
                    ELSE NULL
                END AS perimeter_m,
                ST_NPoints(ST_Force2D(input_geom)) AS points
            FROM analyses
            WHERE id = :analysis_id
            """
        ),
        {"analysis_id": analysis_id},
    ).mappings().first()

    return {
        "perimeter_m": (
            float(row["perimeter_m"])
            if row and row["perimeter_m"] is not None
            else None
        ),
        "points": int(row["points"]) if row and row["points"] else None,
    }


def _result_rows(
    db: Session,
    analysis_id: UUID,
):
    return db.execute(
        select(
            AnalysisResult,
            Source,
            SourceVersion,
        )
        .join(
            Source,
            Source.id == AnalysisResult.source_id,
        )
        .join(
            SourceVersion,
            SourceVersion.id == AnalysisResult.source_version_id,
        )
        .where(
            AnalysisResult.analysis_id == analysis_id
        )
        .order_by(
            AnalysisResult.intersects.desc(),
            Source.institution,
            Source.name,
        )
    ).all()


def _snapshot(
    db: Session,
    analysis: Analysis,
    issuer: User,
    tracking_code: str,
    issued_at: datetime,
) -> dict:
    executor = (
        db.get(User, analysis.created_by_user_id)
        if analysis.created_by_user_id
        else None
    )

    metrics = _analysis_metrics(db, analysis.id)
    rows = _result_rows(db, analysis.id)

    results = []

    for result, source, version in rows:
        results.append(
            {
                "source_id": str(source.id),
                "source_name": source.name,
                "institution": source.institution,
                "source_version_id": str(version.id),
                "reference_date": (
                    version.reference_date.isoformat()
                    if version.reference_date
                    else None
                ),
                "intersects": bool(result.intersects),
                "matched_features": int(result.matched_features or 0),
                "overlap_hectares": float(result.overlap_hectares or 0),
                "overlap_percent": float(result.overlap_percent or 0),
                "nearest_distance_meters": (
                    float(result.nearest_distance_meters)
                    if result.nearest_distance_meters is not None
                    else None
                ),
                "access_mode": (result.details or {}).get(
                    "access_mode",
                    "LOCAL_VECTOR",
                ),
            }
        )

    return {
        "tracking_code": tracking_code,
        "system": "Amazonika Geoespacial",
        "analysis_id": str(analysis.id),
        "analysis_name": analysis.name,
        "geometry_kind": analysis.geometry_kind,
        "area_hectares": analysis.area_hectares,
        "perimeter_meters": metrics["perimeter_m"],
        "vertices_count": metrics["points"],
        "analysis_created_at": (
            analysis.created_at.isoformat()
            if analysis.created_at
            else None
        ),
        "issued_at": issued_at.isoformat(),
        "executor": {
            "id": str(executor.id) if executor else None,
            "name": executor.full_name if executor else "Não identificado",
            "email": executor.email if executor else None,
        },
        "issuer": {
            "id": str(issuer.id),
            "name": issuer.full_name,
            "email": issuer.email,
        },
        "warnings": list(analysis.warnings_json or []),
        "source_statuses": list(analysis.source_status_json or []),
        "results": results,
    }


def build_analysis_map(
    db: Session,
    analysis: Analysis,
    snapshot: dict,
    output_path: Path,
) -> None:
    subject = _subject_geojson(db, analysis.id)

    buffer_m = _context_buffer_m(
        snapshot.get("area_hectares")
    )

    extent_geometry = _context_extent_geojson(
        db,
        analysis.id,
        buffer_m,
    )

    contexts = []
    overlaps = []

    for index, row in enumerate(snapshot["results"]):
        version_id = UUID(row["source_version_id"])
        color = PALETTE[index % len(PALETTE)]

        context_geom, context_count = _context_geojson(
            db,
            analysis.id,
            version_id,
            buffer_m,
        )

        if context_geom:
            contexts.append(
                {
                    "name": row["source_name"],
                    "institution": row["institution"],
                    "geometry": context_geom,
                    "color": color,
                    "intersects": bool(row["intersects"]),
                    "feature_count": context_count,
                }
            )

        if not row["intersects"]:
            continue

        overlap_geom = _overlap_geojson(
            db,
            analysis.id,
            version_id,
        )

        if overlap_geom:
            overlaps.append(
                {
                    "name": row["source_name"],
                    "institution": row["institution"],
                    "geometry": overlap_geom,
                    "color": color,
                }
            )

    # O enquadramento é determinado pelo buffer do imóvel, e não
    # somente pela extensão das áreas efetivamente sobrepostas.
    bbox = _bbox([extent_geometry])

    width = 1600
    height = 1050

    image = Image.new(
        "RGB",
        (width, height),
        "#f6f8f7",
    )

    draw = ImageDraw.Draw(image, "RGBA")

    title_font = _font(34, True)
    subtitle_font = _font(21, False)
    normal_font = _font(18, False)
    small_font = _font(15, False)
    bold_small_font = _font(15, True)

    draw.rectangle(
        (0, 0, width, 100),
        fill="#173f32",
    )

    draw.text(
        (45, 22),
        "AMAZONIKA GEOESPACIAL",
        font=title_font,
        fill="#ffffff",
    )

    draw.text(
        (45, 62),
        f"Mapa da análise · {snapshot['tracking_code']}",
        font=subtitle_font,
        fill="#d8e8e1",
    )

    map_left = 55
    map_top = 135
    map_right = 1545
    map_bottom = 790

    draw.rectangle(
        (map_left, map_top, map_right, map_bottom),
        fill="#ffffff",
        outline="#b8c8c1",
        width=2,
    )

    project = _projector(
        bbox,
        map_left + 30,
        map_top + 30,
        map_right - 30,
        map_bottom - 30,
    )

    minx, miny, maxx, maxy = bbox

    for step in range(1, 5):
        x = map_left + int(
            (map_right - map_left) * step / 5
        )
        y = map_top + int(
            (map_bottom - map_top) * step / 5
        )

        draw.line(
            (x, map_top, x, map_bottom),
            fill="#e7ece9",
            width=1,
        )
        draw.line(
            (map_left, y, map_right, y),
            fill="#e7ece9",
            width=1,
        )

    # Contexto territorial: feições existentes ao redor do imóvel.
    # Interferentes mantêm a cor da base; demais aparecem discretamente.
    for item in contexts:
        context_outline = (
            item["color"]
            if item["intersects"]
            else "#91a09a"
        )

        _draw_geometry(
            draw,
            item["geometry"],
            project,
            outline=context_outline,
            fill=None,
            width=2,
        )

    # Sobreposição exata: somente a parcela da feição que realmente
    # intersecta a geometria analisada recebe preenchimento forte.
    for item in overlaps:
        color = item["color"]
        fill = color + "55"

        _draw_geometry(
            draw,
            item["geometry"],
            project,
            outline=color,
            fill=fill,
            width=4,
        )

    _draw_geometry(
        draw,
        subject,
        project,
        outline="#075f3f",
        fill="#1d9a6650",
        width=7,
    )

    # Norte
    north_x = map_right - 65
    north_y = map_top + 55

    draw.text(
        (north_x - 8, north_y - 38),
        "N",
        font=_font(22, True),
        fill="#173f32",
    )

    draw.polygon(
        [
            (north_x, north_y - 8),
            (north_x - 12, north_y + 25),
            (north_x + 12, north_y + 25),
        ],
        fill="#173f32",
    )

    # Escala gráfica aproximada
    scale_m, scale_px = _map_scale_meters(
        bbox,
        map_right - map_left,
    )

    sx = map_left + 35
    sy = map_bottom - 35

    draw.line(
        (sx, sy, sx + scale_px, sy),
        fill="#173f32",
        width=5,
    )

    draw.line(
        (sx, sy - 7, sx, sy + 7),
        fill="#173f32",
        width=3,
    )

    draw.line(
        (
            sx + scale_px,
            sy - 7,
            sx + scale_px,
            sy + 7,
        ),
        fill="#173f32",
        width=3,
    )

    scale_label = (
        f"{int(scale_m / 1000)} km"
        if scale_m >= 1000
        else f"{int(scale_m)} m"
    )

    draw.text(
        (sx, sy - 29),
        scale_label,
        font=small_font,
        fill="#173f32",
    )

    legend_y = 825

    draw.text(
        (55, legend_y),
        "LEGENDA",
        font=bold_small_font,
        fill="#173f32",
    )

    legend_y += 35

    draw.rectangle(
        (55, legend_y, 78, legend_y + 18),
        fill="#1d9a6650",
        outline="#075f3f",
        width=3,
    )

    draw.text(
        (90, legend_y - 2),
        "Área analisada",
        font=normal_font,
        fill="#213c32",
    )

    legend_y += 34

    for item in overlaps[:5]:
        draw.rectangle(
            (55, legend_y, 78, legend_y + 18),
            fill=item["color"] + "55",
            outline=item["color"],
            width=3,
        )

        label = f"{item['institution']} · {item['name']}"

        draw.text(
            (90, legend_y - 2),
            label[:95],
            font=normal_font,
            fill="#213c32",
        )

        legend_y += 30

    result_count = sum(
        1
        for row in snapshot["results"]
        if row["intersects"]
    )

    result_text = (
        f"{result_count} fonte(s) apresentaram interferência espacial."
        if result_count
        else (
            "Nenhuma sobreposição espacial identificada nas "
            "bases efetivamente consultadas."
        )
    )

    draw.text(
        (850, 830),
        "RESULTADO CARTOGRÁFICO",
        font=bold_small_font,
        fill="#173f32",
    )

    draw.multiline_text(
        (850, 865),
        result_text,
        font=normal_font,
        fill="#213c32",
        spacing=7,
    )

    draw.text(
        (850, 940),
        (
            f"Área: {_fmt_number(snapshot.get('area_hectares'))} ha  ·  "
            "SRC: SIRGAS 2000 / EPSG:4674"
        ),
        font=small_font,
        fill="#566d64",
    )

    draw.text(
        (850, 970),
        f"Análise: {_fmt_datetime(analysis.created_at)}",
        font=small_font,
        fill="#566d64",
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    image.save(
        output_path,
        format="PNG",
        optimize=True,
    )


def _qr_png(url: str) -> bytes:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)

    image = qr.make_image(
        fill_color="black",
        back_color="white",
    )

    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()



def _register_pdf_fonts() -> None:
    fonts = {
        "AmazonikaSans": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "AmazonikaSansBold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "AmazonikaSerif": "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "AmazonikaSerifBold": "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    }

    registered = set(pdfmetrics.getRegisteredFontNames())

    for name, path in fonts.items():
        if name in registered:
            continue
        try:
            pdfmetrics.registerFont(TTFont(name, path))
        except Exception:
            pass


def _pdf_font(name: str, fallback: str) -> str:
    return name if name in pdfmetrics.getRegisteredFontNames() else fallback


def _company_logo_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "assets"
        / "amazonika-logo.png"
    )


def _sanitize_report_warning(value: str) -> str:
    raw = (value or "").strip()

    if not raw:
        return "Ocorrência registrada durante a consulta da fonte."

    source_name = raw.split(":", 1)[0].strip()

    lowered = raw.lower()

    if (
        "curl" in lowered
        or "/tmp/" in lowered
        or "http://" in lowered
        or "https://" in lowered
        or "--connect-timeout" in lowered
        or "--max-time" in lowered
        or "command '['" in lowered
    ):
        if "cadastro ambiental rural" in lowered or "sicar" in lowered:
            return (
                "Cadastro Ambiental Rural (CAR): o serviço de consulta "
                "do SICAR não respondeu adequadamente durante esta análise."
            )

        return (
            f"{source_name}: a fonte não respondeu adequadamente "
            "durante a execução da análise."
        )

    if len(raw) > 280:
        raw = raw[:277].rstrip() + "..."

    return raw


def _execution_rows_for_report(snapshot: dict) -> list[dict]:
    rows = list(snapshot.get("source_statuses") or [])

    if rows:
        return rows

    return [
        {
            "source_id": row.get("source_id"),
            "source_name": row.get("source_name"),
            "institution": row.get("institution"),
            "status": "ANALYZED",
            "message": None,
            "access_mode": row.get("access_mode"),
            "source_version_id": row.get("source_version_id"),
            "reference_date": row.get("reference_date"),
            "intersects": row.get("intersects"),
            "matched_features": row.get("matched_features"),
            "overlap_hectares": row.get("overlap_hectares"),
            "overlap_percent": row.get("overlap_percent"),
            "nearest_distance_meters": row.get("nearest_distance_meters"),
        }
        for row in snapshot.get("results", [])
    ]


def _pdf_styles():
    _register_pdf_fonts()

    sans = _pdf_font("AmazonikaSans", "Helvetica")
    sans_bold = _pdf_font("AmazonikaSansBold", "Helvetica-Bold")
    serif = _pdf_font("AmazonikaSerif", "Times-Roman")
    serif_bold = _pdf_font("AmazonikaSerifBold", "Times-Bold")

    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="AmazonikaCoverTitle",
            parent=styles["Title"],
            fontName=serif_bold,
            fontSize=21,
            leading=25,
            textColor=colors.HexColor("#173f32"),
            spaceAfter=3,
        )
    )

    styles.add(
        ParagraphStyle(
            name="AmazonikaSubtitle",
            parent=styles["BodyText"],
            fontName=sans,
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#5b6f66"),
        )
    )

    styles.add(
        ParagraphStyle(
            name="AmazonikaSection",
            parent=styles["Heading2"],
            fontName=sans_bold,
            fontSize=10.5,
            leading=13,
            textColor=colors.HexColor("#173f32"),
            spaceBefore=7,
            spaceAfter=5,
            keepWithNext=True,
        )
    )

    styles.add(
        ParagraphStyle(
            name="AmazonikaBody",
            parent=styles["BodyText"],
            fontName=sans,
            fontSize=8,
            leading=11.3,
            alignment=TA_JUSTIFY,
            textColor=colors.HexColor("#263c33"),
        )
    )

    styles.add(
        ParagraphStyle(
            name="AmazonikaSmall",
            parent=styles["BodyText"],
            fontName=sans,
            fontSize=6.7,
            leading=8.8,
            textColor=colors.HexColor("#60736b"),
        )
    )

    styles.add(
        ParagraphStyle(
            name="AmazonikaSmallCenter",
            parent=styles["BodyText"],
            fontName=sans,
            fontSize=6.5,
            leading=8.3,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#60736b"),
        )
    )

    styles.add(
        ParagraphStyle(
            name="AmazonikaCardLabel",
            parent=styles["BodyText"],
            fontName=sans_bold,
            fontSize=6.2,
            leading=8,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#60736b"),
        )
    )

    styles.add(
        ParagraphStyle(
            name="AmazonikaCardValue",
            parent=styles["BodyText"],
            fontName=serif_bold,
            fontSize=13,
            leading=16,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#173f32"),
        )
    )

    styles.add(
        ParagraphStyle(
            name="AmazonikaTable",
            parent=styles["BodyText"],
            fontName=sans,
            fontSize=5.7,
            leading=7.2,
            textColor=colors.HexColor("#263c33"),
        )
    )

    styles.add(
        ParagraphStyle(
            name="AmazonikaTableBold",
            parent=styles["BodyText"],
            fontName=sans_bold,
            fontSize=5.7,
            leading=7.2,
            textColor=colors.HexColor("#173f32"),
        )
    )

    return styles


def build_report_pdf(
    snapshot: dict,
    map_path: Path,
    pdf_path: Path,
    verification_url: str,
) -> None:
    _register_pdf_fonts()
    styles = _pdf_styles()

    sans = _pdf_font("AmazonikaSans", "Helvetica")
    sans_bold = _pdf_font("AmazonikaSansBold", "Helvetica-Bold")
    serif_bold = _pdf_font("AmazonikaSerifBold", "Times-Bold")

    green = colors.HexColor("#173f32")
    green_2 = colors.HexColor("#245c49")
    green_light = colors.HexColor("#eef5f1")
    green_line = colors.HexColor("#b7cbc1")
    text_dark = colors.HexColor("#263c33")
    text_muted = colors.HexColor("#61736b")
    red = colors.HexColor("#a33d36")
    red_light = colors.HexColor("#faecea")
    amber = colors.HexColor("#8a5a12")
    amber_light = colors.HexColor("#fff4dd")

    qr_buffer = io.BytesIO(_qr_png(verification_url))

    execution_rows = _execution_rows_for_report(snapshot)

    expected_count = len(execution_rows)
    analyzed_count = sum(
        1 for row in execution_rows
        if row.get("status") == "ANALYZED"
    )
    overlap_count = sum(
        1 for row in execution_rows
        if row.get("status") == "ANALYZED"
        and row.get("intersects") is True
    )
    clear_count = sum(
        1 for row in execution_rows
        if row.get("status") == "ANALYZED"
        and row.get("intersects") is False
    )
    alert_count = sum(
        1 for row in execution_rows
        if row.get("status") in {"UNAVAILABLE", "FAILED"}
    )

    executor = snapshot["executor"]
    issuer = snapshot["issuer"]

    analysis_dt = (
        datetime.fromisoformat(snapshot["analysis_created_at"])
        if snapshot.get("analysis_created_at")
        else None
    )
    issued_dt = datetime.fromisoformat(snapshot["issued_at"])

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=25 * mm,
        bottomMargin=18 * mm,
        title=f"Relatório Territorial {snapshot['tracking_code']}",
        author="Amazonika Engenharia",
        subject="Análise Territorial",
    )

    story = []

    # --------------------------------------------------------
    # CAPA / IDENTIFICAÇÃO INSTITUCIONAL
    # --------------------------------------------------------

    logo_path = _company_logo_path()

    if logo_path.exists():
        logo = RLImage(
            str(logo_path),
            width=24 * mm,
            height=24 * mm,
        )
    else:
        logo = Paragraph(
            "<b>AMAZONIKA</b>",
            styles["AmazonikaBody"],
        )

    company_text = Paragraph(
        "<font size='11'><b>AMAZONIKA ENGENHARIA LTDA</b></font><br/>"
        "<font size='7.3'>TOPOGRAFIA E MEIO AMBIENTE</font>",
        styles["AmazonikaBody"],
    )

    company_contact = Paragraph(
        "<para align='right'>"
        "<b>AMAZONIKA ENGENHARIA LTDA</b><br/>"
        "Av. Almirante Barroso 620-B - CEP 68900-401<br/>"
        "Bairro: Central - Macapá/AP<br/>"
        "CNPJ: 49.158.834/0001-19<br/>"
        "Contato: 96 98803-6439 / 96 9141-0943<br/>"
        "www.amazonikaengenharia.com.br<br/>"
        "amazonika@amazonikaengenharia.com.br"
        "</para>",
        styles["AmazonikaSmall"],
    )

    institutional_header = Table(
        [
            [logo, company_text, company_contact],
        ],
        colWidths=[28 * mm, 53 * mm, 91 * mm],
        rowHeights=[34 * mm],
    )

    institutional_header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                ("LINEBELOW", (0, 0), (-1, 0), 1.2, green),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    story.append(institutional_header)
    story.append(Spacer(1, 7 * mm))

    story.append(
        Paragraph(
            "RELATÓRIO DE ANÁLISE TERRITORIAL",
            styles["AmazonikaCoverTitle"],
        )
    )

    story.append(
        Paragraph(
            snapshot["analysis_name"],
            styles["AmazonikaSubtitle"],
        )
    )

    story.append(Spacer(1, 2 * mm))

    tracking_box = Table(
        [
            [
                Paragraph(
                    "<b>CÓDIGO DE RASTREIO</b>",
                    styles["AmazonikaCardLabel"],
                ),
                Paragraph(
                    f"<b>{snapshot['tracking_code']}</b>",
                    styles["AmazonikaCardValue"],
                ),
                Paragraph(
                    f"Emitido em<br/><b>{_fmt_datetime(issued_dt)}</b>",
                    styles["AmazonikaSmallCenter"],
                ),
            ]
        ],
        colWidths=[45 * mm, 72 * mm, 55 * mm],
    )

    tracking_box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), green_light),
                ("BOX", (0, 0), (-1, -1), 0.6, green_line),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    story.append(tracking_box)
    story.append(Spacer(1, 5 * mm))

    cards = Table(
        [
            [
                Paragraph("ÁREA ANALISADA", styles["AmazonikaCardLabel"]),
                Paragraph("BASES ANALISADAS", styles["AmazonikaCardLabel"]),
                Paragraph("INTERFERÊNCIAS", styles["AmazonikaCardLabel"]),
                Paragraph("ALERTAS", styles["AmazonikaCardLabel"]),
            ],
            [
                Paragraph(
                    (
                        "Ponto"
                        if snapshot.get("area_hectares") is None
                        else f"{_fmt_number(snapshot.get('area_hectares'))} ha"
                    ),
                    styles["AmazonikaCardValue"],
                ),
                Paragraph(
                    f"{analyzed_count}/{expected_count}",
                    styles["AmazonikaCardValue"],
                ),
                Paragraph(
                    str(overlap_count),
                    styles["AmazonikaCardValue"],
                ),
                Paragraph(
                    str(alert_count),
                    styles["AmazonikaCardValue"],
                ),
            ],
        ],
        colWidths=[43 * mm, 43 * mm, 43 * mm, 43 * mm],
    )

    cards.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.5, green_line),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, green_line),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    story.append(cards)

    story.append(
        Paragraph(
            "1. IDENTIFICAÇÃO DA ANÁLISE",
            styles["AmazonikaSection"],
        )
    )

    identification = [
        ["Sistema emissor", snapshot["system"]],
        ["Responsável pela análise", executor["name"]],
        ["Usuário emissor", issuer["name"]],
        ["Data/hora da análise", _fmt_datetime(analysis_dt)],
        ["Data/hora da emissão", _fmt_datetime(issued_dt)],
        ["Geometria", snapshot.get("geometry_kind") or "—"],
        ["SRC", "SIRGAS 2000 · EPSG:4674"],
        [
            "Perímetro",
            (
                f"{_fmt_number(snapshot.get('perimeter_meters'), 2)} m"
                if snapshot.get("perimeter_meters") is not None
                else "—"
            ),
        ],
    ]

    info_table = Table(
        identification,
        colWidths=[48 * mm, 124 * mm],
    )

    info_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), green_light),
                ("TEXTCOLOR", (0, 0), (0, -1), green),
                ("FONTNAME", (0, 0), (0, -1), sans_bold),
                ("FONTNAME", (1, 0), (1, -1), sans),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.25, green_line),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    story.append(info_table)

    story.append(
        Paragraph(
            "2. MAPA DE CONTEXTO TERRITORIAL",
            styles["AmazonikaSection"],
        )
    )

    map_image = RLImage(
        str(map_path),
        width=172 * mm,
        height=112.9 * mm,
    )

    map_panel = Table(
        [[map_image]],
        colWidths=[174 * mm],
    )

    map_panel.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.6, green_line),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("LEFTPADDING", (0, 0), (-1, -1), 1),
                ("RIGHTPADDING", (0, 0), (-1, -1), 1),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]
        )
    )

    story.append(map_panel)

    story.append(
        Paragraph(
            "Figura 1 — Contexto territorial da área analisada, incluindo "
            "feições existentes no entorno e destaque das interferências "
            "espaciais identificadas.",
            styles["AmazonikaSmall"],
        )
    )

    # --------------------------------------------------------
    # BASES TERRITORIAIS
    # --------------------------------------------------------

    story.append(
        Paragraph(
            "3. BASES TERRITORIAIS CONSULTADAS",
            styles["AmazonikaSection"],
        )
    )

    execution_summary = Table(
        [
            [
                "Previstas",
                "Analisadas",
                "Interferem",
                "Sem interferência",
                "Indisponíveis / falha",
            ],
            [
                str(expected_count),
                str(analyzed_count),
                str(overlap_count),
                str(clear_count),
                str(alert_count),
            ],
        ],
        colWidths=[
            32 * mm,
            32 * mm,
            32 * mm,
            38 * mm,
            38 * mm,
        ],
    )

    execution_summary.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), green),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 1), (-1, 1), green_light),
                ("TEXTCOLOR", (0, 1), (-1, 1), green),
                ("FONTNAME", (0, 0), (-1, -1), sans_bold),
                ("FONTSIZE", (0, 0), (-1, -1), 6.3),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.25, green_line),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    story.append(execution_summary)
    story.append(Spacer(1, 3 * mm))

    source_table = [
        [
            "Fonte",
            "Órgão",
            "Situação",
            "Feições",
            "Área (ha)",
            "%",
            "Distância",
            "Referência",
        ]
    ]

    row_states = []

    for row in execution_rows:
        status = row.get("status")

        if status == "ANALYZED":
            if row.get("intersects") is True:
                situation = "INTERFERE"
                state = "INTERFERE"
            else:
                situation = "SEM INTERFERÊNCIA"
                state = "CLEAR"

            features = str(row.get("matched_features") or 0)
            area = _fmt_number(row.get("overlap_hectares") or 0)
            percent = _fmt_number(row.get("overlap_percent") or 0, 2)

            distance_value = row.get("nearest_distance_meters")
            distance = (
                f"{_fmt_number(distance_value, 2)} m"
                if distance_value is not None
                else "—"
            )

        elif status == "UNAVAILABLE":
            situation = "INDISPONÍVEL"
            state = "UNAVAILABLE"
            features = "—"
            area = "—"
            percent = "—"
            distance = "—"

        else:
            situation = "FALHA"
            state = "FAILED"
            features = "—"
            area = "—"
            percent = "—"
            distance = "—"

        source_table.append(
            [
                Paragraph(
                    str(row.get("source_name") or "—"),
                    styles["AmazonikaTable"],
                ),
                Paragraph(
                    str(row.get("institution") or "—"),
                    styles["AmazonikaTable"],
                ),
                Paragraph(
                    situation,
                    styles["AmazonikaTableBold"],
                ),
                features,
                area,
                percent,
                distance,
                row.get("reference_date") or "—",
            ]
        )

        row_states.append(state)

    sources = Table(
        source_table,
        repeatRows=1,
        colWidths=[
            38 * mm,
            21 * mm,
            27 * mm,
            13 * mm,
            18 * mm,
            11 * mm,
            20 * mm,
            24 * mm,
        ],
    )

    source_style = [
        ("BACKGROUND", (0, 0), (-1, 0), green),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), sans_bold),
        ("FONTNAME", (3, 1), (-1, -1), sans),
        ("FONTSIZE", (0, 0), (-1, -1), 5.4),
        ("GRID", (0, 0), (-1, -1), 0.22, colors.HexColor("#d3dfd9")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.1),
    ]

    for table_row, state in enumerate(row_states, start=1):
        if table_row % 2 == 0:
            source_style.append(
                (
                    "BACKGROUND",
                    (0, table_row),
                    (-1, table_row),
                    colors.HexColor("#f8faf9"),
                )
            )

        if state == "INTERFERE":
            source_style.extend(
                [
                    ("BACKGROUND", (2, table_row), (2, table_row), red_light),
                    ("TEXTCOLOR", (2, table_row), (2, table_row), red),
                ]
            )

        elif state == "CLEAR":
            source_style.extend(
                [
                    ("BACKGROUND", (2, table_row), (2, table_row), green_light),
                    ("TEXTCOLOR", (2, table_row), (2, table_row), green_2),
                ]
            )

        else:
            source_style.extend(
                [
                    ("BACKGROUND", (2, table_row), (2, table_row), amber_light),
                    ("TEXTCOLOR", (2, table_row), (2, table_row), amber),
                ]
            )

    sources.setStyle(TableStyle(source_style))
    story.append(sources)

    unavailable_or_failed = [
        row for row in execution_rows
        if row.get("status") in {"UNAVAILABLE", "FAILED"}
    ]

    if unavailable_or_failed:
        story.append(Spacer(1, 3 * mm))
        story.append(
            Paragraph(
                "<b>Nota de cobertura:</b> fontes classificadas como "
                "INDISPONÍVEL ou FALHA não foram utilizadas para concluir "
                "ausência ou presença de sobreposição. A situação corresponde "
                "ao momento exato desta análise.",
                styles["AmazonikaSmall"],
            )
        )

    # --------------------------------------------------------
    # RESULTADO EXECUTIVO
    # --------------------------------------------------------

    overlaps = [
        row for row in snapshot.get("results", [])
        if row.get("intersects")
    ]

    story.append(
        Paragraph(
            "4. RESULTADO DA ANÁLISE",
            styles["AmazonikaSection"],
        )
    )

    if overlaps:
        conclusion = (
            f"Foram identificadas interferências espaciais em "
            f"{len(overlaps)} fonte(s) territorial(is). "
            "As ocorrências devem ser avaliadas em conjunto com os atos, "
            "cadastros e documentos emitidos pelos órgãos responsáveis. "
            "Os percentuais apresentados por fonte não devem ser somados "
            "como área territorial única quando houver coincidência entre "
            "bases ou recortes do mesmo universo cadastral."
        )
        result_bg = red_light
        result_color = red
        result_title = "INTERFERÊNCIAS IDENTIFICADAS"
    else:
        conclusion = (
            "Não foram identificadas sobreposições espaciais entre a "
            "geometria analisada e as feições disponíveis nas bases "
            "territoriais efetivamente consultadas, consideradas suas "
            "respectivas versões e datas de atualização."
        )
        result_bg = green_light
        result_color = green_2
        result_title = "SEM INTERFERÊNCIA IDENTIFICADA"

    result_box = Table(
        [
            [
                Paragraph(
                    f"<b>{result_title}</b><br/><br/>{conclusion}",
                    styles["AmazonikaBody"],
                )
            ]
        ],
        colWidths=[172 * mm],
    )

    result_box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), result_bg),
                ("BOX", (0, 0), (-1, -1), 0.7, result_color),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )

    story.append(result_box)

    if overlaps:
        story.append(
            Paragraph(
                "5. INTERFERÊNCIAS RELEVANTES",
                styles["AmazonikaSection"],
            )
        )

        overlap_table = [
            ["Fonte", "Órgão", "Feições", "Área (ha)", "% da área"]
        ]

        for row in overlaps:
            overlap_table.append(
                [
                    Paragraph(
                        str(row.get("source_name") or "—"),
                        styles["AmazonikaTable"],
                    ),
                    Paragraph(
                        str(row.get("institution") or "—"),
                        styles["AmazonikaTable"],
                    ),
                    str(row.get("matched_features") or 0),
                    _fmt_number(row.get("overlap_hectares") or 0),
                    _fmt_number(row.get("overlap_percent") or 0, 2),
                ]
            )

        overlap_tbl = Table(
            overlap_table,
            repeatRows=1,
            colWidths=[
                62 * mm,
                32 * mm,
                22 * mm,
                29 * mm,
                27 * mm,
            ],
        )

        overlap_tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), red),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), sans_bold),
                    ("FONTNAME", (2, 1), (-1, -1), sans),
                    ("FONTSIZE", (0, 0), (-1, -1), 6),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dfcbc8")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )

        story.append(overlap_tbl)

    # --------------------------------------------------------
    # ADVERTÊNCIAS SANITIZADAS
    # --------------------------------------------------------

    sanitized_warnings = []

    for warning in snapshot.get("warnings") or []:
        cleaned = _sanitize_report_warning(str(warning))
        if cleaned and cleaned not in sanitized_warnings:
            sanitized_warnings.append(cleaned)

    if sanitized_warnings:
        story.append(
            Paragraph(
                "6. ADVERTÊNCIAS DA EXECUÇÃO",
                styles["AmazonikaSection"],
            )
        )

        warning_rows = []

        for warning in sanitized_warnings:
            warning_rows.append(
                [
                    Paragraph("!", styles["AmazonikaCardValue"]),
                    Paragraph(warning, styles["AmazonikaBody"]),
                ]
            )

        warning_table = Table(
            warning_rows,
            colWidths=[10 * mm, 162 * mm],
        )

        warning_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), amber_light),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e6c681")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TEXTCOLOR", (0, 0), (0, -1), amber),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )

        story.append(warning_table)

    # --------------------------------------------------------
    # LIMITAÇÕES + VERIFICAÇÃO, SEM PÁGINA VAZIA FORÇADA
    # --------------------------------------------------------

    story.append(
        Paragraph(
            "LIMITAÇÕES E RESPONSABILIDADE TÉCNICA",
            styles["AmazonikaSection"],
        )
    )

    story.append(
        Paragraph(
            "Os resultados refletem exclusivamente as bases, versões e "
            "geometrias efetivamente disponíveis e processadas na data da "
            "análise. A ausência de interferência não constitui certidão "
            "negativa e não substitui documentos, anuências, certidões ou "
            "manifestações formais dos órgãos competentes.",
            styles["AmazonikaBody"],
        )
    )

    story.append(Spacer(1, 5 * mm))

    qr_image = RLImage(
        qr_buffer,
        width=31 * mm,
        height=31 * mm,
    )

    verification = Table(
        [
            [
                qr_image,
                Paragraph(
                    "<font size='9'><b>VERIFICAÇÃO E RASTREABILIDADE</b></font>"
                    "<br/><br/>"
                    f"Código: <b>{snapshot['tracking_code']}</b><br/>"
                    f"Sistema: {snapshot['system']}<br/>"
                    f"Emissor: {issuer['name']}<br/>"
                    f"Emissão: {_fmt_datetime(issued_dt)}<br/><br/>"
                    "Aponte a câmera do celular para o QR Code para consultar "
                    "a emissão registrada e acessar o documento vinculado.",
                    styles["AmazonikaBody"],
                ),
                Paragraph(
                    "<font size='6'><b>AMAZONIKA ENGENHARIA LTDA</b></font><br/>"
                    "Av. Almirante Barroso 620-B<br/>"
                    "CEP 68900-401<br/>"
                    "Bairro: Central - Macapá/AP<br/>"
                    "CNPJ: 49.158.834/0001-19<br/>"
                    "Contato: 96 98803-6439 / 96 9141-0943<br/>"
                    "www.amazonikaengenharia.com.br<br/>"
                    "amazonika@amazonikaengenharia.com.br",
                    styles["AmazonikaSmall"],
                ),
            ]
        ],
        colWidths=[36 * mm, 87 * mm, 49 * mm],
    )

    verification.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), green_light),
                ("BOX", (0, 0), (-1, -1), 0.8, green_line),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    story.append(verification)

    # --------------------------------------------------------
    # CABEÇALHO / RODAPÉ DE TODAS AS PÁGINAS
    # --------------------------------------------------------

    def page_decoration(canvas, doc):
        canvas.saveState()

        page_width, page_height = A4

        # Cabeçalho discreto nas páginas internas.
        if doc.page > 1:
            canvas.setStrokeColor(green_line)
            canvas.setLineWidth(0.6)
            canvas.line(
                14 * mm,
                page_height - 15 * mm,
                page_width - 14 * mm,
                page_height - 15 * mm,
            )

            if logo_path.exists():
                try:
                    canvas.drawImage(
                        str(logo_path),
                        14 * mm,
                        page_height - 13.2 * mm,
                        width=8 * mm,
                        height=8 * mm,
                        preserveAspectRatio=True,
                        mask="auto",
                    )
                except Exception:
                    pass

            canvas.setFont(sans_bold, 6.8)
            canvas.setFillColor(green)
            canvas.drawString(
                24 * mm,
                page_height - 10.5 * mm,
                "AMAZONIKA ENGENHARIA",
            )

            canvas.setFont(sans, 5.8)
            canvas.setFillColor(text_muted)
            canvas.drawRightString(
                page_width - 14 * mm,
                page_height - 10.5 * mm,
                "RELATÓRIO DE ANÁLISE TERRITORIAL",
            )

        # Rodapé.
        canvas.setStrokeColor(green_line)
        canvas.setLineWidth(0.5)
        canvas.line(
            14 * mm,
            13 * mm,
            page_width - 14 * mm,
            13 * mm,
        )

        canvas.setFont(sans, 6)
        canvas.setFillColor(text_muted)

        canvas.drawString(
            14 * mm,
            8 * mm,
            f"Amazonika Geoespacial · {snapshot['tracking_code']}",
        )

        canvas.drawCentredString(
            page_width / 2,
            8 * mm,
            "CNPJ 49.158.834/0001-19",
        )

        canvas.drawRightString(
            page_width - 14 * mm,
            8 * mm,
            f"Página {doc.page}",
        )

        canvas.restoreState()

    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    doc.build(
        story,
        onFirstPage=page_decoration,
        onLaterPages=page_decoration,
    )


def issue_territorial_report(
    db: Session,
    analysis: Analysis,
    issuer: User,
) -> ReportEmission:
    if analysis.status != "COMPLETED":
        raise ValueError(
            "A análise precisa estar concluída antes da emissão do relatório."
        )

    settings = get_settings()

    issued_at = datetime.now(timezone.utc)

    tracking_code = (
        f"AG-{issued_at.astimezone(LOCAL_TZ).year}-"
        f"{uuid4().hex[:8].upper()}"
    )

    public_token = secrets.token_urlsafe(32)

    report_dir = (
        Path(settings.storage_dir)
        / "reports"
        / tracking_code
    )

    report_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    map_path = report_dir / "mapa-analise.png"
    pdf_path = report_dir / "relatorio.pdf"
    metadata_path = report_dir / "metadata.json"

    snapshot = _snapshot(
        db,
        analysis,
        issuer,
        tracking_code,
        issued_at,
    )

    emission = ReportEmission(
        analysis_id=analysis.id,
        issued_by_user_id=issuer.id,
        tracking_code=tracking_code,
        public_token=public_token,
        issued_at=issued_at,
        status="GENERATING",
        analysis_name=analysis.name,
        analysis_snapshot=snapshot,
    )

    db.add(emission)
    db.commit()
    db.refresh(emission)

    try:
        verification_url = (
            f"{settings.public_base_url.rstrip('/')}"
            f"/api/v1/reports/verify/{public_token}"
        )

        build_analysis_map(
            db,
            analysis,
            snapshot,
            map_path,
        )

        build_report_pdf(
            snapshot,
            map_path,
            pdf_path,
            verification_url,
        )

        digest = hashlib.sha256(
            pdf_path.read_bytes()
        ).hexdigest()

        metadata = {
            "tracking_code": tracking_code,
            "public_token": public_token,
            "pdf_sha256": digest,
            "analysis_snapshot": snapshot,
        }

        metadata_path.write_text(
            json.dumps(
                metadata,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        emission.status = "READY"
        emission.pdf_path = str(pdf_path)
        emission.map_path = str(map_path)
        emission.pdf_sha256 = digest
        emission.error_message = None

        db.commit()
        db.refresh(emission)

        return emission

    except Exception as exc:
        emission.status = "FAILED"
        emission.error_message = str(exc)[:2000]
        db.commit()
        raise
