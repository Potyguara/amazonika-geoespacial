from __future__ import annotations

import base64
import io
import math
import textwrap
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo
from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth

from PIL import Image
from pyproj import CRS, Geod, Transformer
from reportlab.lib.pagesizes import A0, A1, A2, A3, A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from shapely.geometry import Polygon, shape

from app.services.plant_memorial import _logo_path, load_document_template

DISCLAIMER = (
    "Este documento se trata apenas de um croqui, nao representa o polígono "
    "com coordenadas precisas, os pontos nao foram coletados com equipamentos "
    "GNSS de alta precisão."
)
SIZES = [("A3", landscape(A3)),
         ("A2", landscape(A2)), ("A1", landscape(A1)), ("A0", landscape(A0))]
SCALES = [100, 200, 250, 500, 750, 1000, 1500, 2000, 2500, 5000, 7500,
          10000, 15000, 20000, 25000, 50000, 100000, 200000, 500000]


@dataclass
class Parcel:
    name: str
    points: list[tuple[float, float]]
    names: list[str]
    area_ha: float
    perimeter: float
    segments: list[dict]
    confrontants: list[str]
    altitudes: list[float | None]
    normal_altitudes: list[float | None]


def prepare_parcels(raw: list[dict]) -> list[Parcel]:
    if not 1 <= len(raw) <= 100:
        raise ValueError("Selecione de 1 a 100 polígonos para uma planta conjunta.")
    geod = Geod(ellps="GRS80")
    output = []
    for index, data in enumerate(raw):
        polygon = shape(data["geometry"])
        if not isinstance(polygon, Polygon) or polygon.is_empty or not polygon.is_valid:
            raise ValueError(f"Área {index + 1}: informe um polígono válido.")
        if len(polygon.interiors):
            raise ValueError(
                f"Área {index + 1}: polígonos com ilhas internas precisam de representação "
                "específica do perímetro antes da emissão."
            )
        # SIGEF/GeoPackage pode fornecer vértices XYZ. Os cálculos geodésicos
        # usam longitude/latitude; o Z não é interpretado como altitude validada.
        points = [(float(coord[0]), float(coord[1]))
                  for coord in list(polygon.exterior.coords)[:-1]]
        if len(points) < 3 or len(points) > 2000:
            raise ValueError(f"Área {index + 1}: número de vértices fora do limite (3 a 2.000).")
        supplied_names = data.get("vertex_names")
        if supplied_names is not None and len(supplied_names) != len(points):
            raise ValueError(f"Área {index + 1}: a lista de nomes dos vértices está incompleta.")
        names = [str(value).strip() for value in supplied_names] if supplied_names is not None else [
            f"P{index + 1:02d}-V{j + 1:02d}" for j in range(len(points))
        ]
        if any(not n or len(n) > 64 for n in names) or len(set(names)) != len(names):
            raise ValueError(f"Área {index + 1}: nomes de vértices inválidos ou repetidos.")
        area, perimeter = geod.geometry_area_perimeter(polygon)
        confrontants = data.get("confrontants") or [""] * len(points)
        altitudes = data.get("altitudes_m") or [None] * len(points)
        normal_altitudes = data.get("normal_altitudes_m") or [None] * len(points)
        if (len(confrontants) != len(points) or len(altitudes) != len(points)
                or len(normal_altitudes) != len(points)):
            raise ValueError(f"Área {index + 1}: confrontantes/altitudes não correspondem aos vértices.")
        segments = []
        for i, (lon, lat) in enumerate(points):
            next_lon, next_lat = points[(i + 1) % len(points)]
            azimuth, _, distance = geod.inv(lon, lat, next_lon, next_lat)
            segments.append({
                "start": names[i],
                "end": names[(i + 1) % len(points)],
                "azimuth": azimuth % 360,
                "distance": distance,
                "lon": lon,
                "lat": lat,
                "next_lon": next_lon,
                "next_lat": next_lat,
            })
        output.append(Parcel(
            name=str(data.get("name") or f"Polígono {index + 1}").strip()[:120],
            points=points, names=names, area_ha=abs(area) / 10000,
            perimeter=perimeter, segments=segments,
            confrontants=[str(item or "").strip()[:250] for item in confrontants],
            altitudes=[float(item) if item is not None else None for item in altitudes],
            normal_altitudes=[float(item) if item is not None else None for item in normal_altitudes],
        ))
    return output


def _br_number(value: float, decimals: int = 2) -> str:
    return f"{value:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _dms(value: float, axis: str) -> str:
    # Negativos explícitos, conforme padrão solicitado no memorial.
    sign = "-" if value < 0 else ""
    absolute = abs(value)
    total_ms = round(absolute * 3600 * 1000)
    degrees, rest = divmod(total_ms, 3600 * 1000)
    minutes, seconds_ms = divmod(rest, 60 * 1000)
    digits = 2 if axis == "lat" else 2
    return f'{sign}{degrees:0{digits}d}°{minutes:02d}\u0027{seconds_ms / 1000:06.3f}"'.replace(".", ",")


def _azimuth_minutes(degrees: float) -> str:
    total = round((degrees % 360) * 60) % (360 * 60)
    degree, minute = divmod(total, 60)
    return f"{degree:02d}°{minute:02d}'"


def build_joint_memorial(
    parcels: list[Parcel], *, title: str, owner: str | None,
    responsible: str | None, croqui: bool,
    owner_rg: str | None = None, owner_cpf: str | None = None,
    property_address: str | None = None,
    memorial_heading: str = "MEMORIAL DESCRITIVO",
    professional: dict | None = None,
    property_metadata: dict[str, str] | None = None,
) -> str:
    """Redação corrida, agrupando trechos contíguos do mesmo confrontante.

    Nunca sintetiza altitude, confrontante ou credenciais ausentes.
    """
    professional = professional or {}
    lines = [
        memorial_heading.upper(), title.upper(), "",
        f"IMÓVEL: {title}",
        f"DETENTOR/POSSEIRO: {owner or 'Não informado'}",
    ]
    if owner_rg:
        lines.append(f"RG: {owner_rg}")
    if owner_cpf:
        lines.append(f"CPF: {owner_cpf}")
    if property_address:
        lines.append(f"LOCALIZAÇÃO: {property_address}")
    for key, label in (
        ("legal_status", "SITUAÇÃO JURÍDICA"),
        ("area_nature", "NATUREZA DA ÁREA"),
        ("sncr", "CÓDIGO SNCR/INCRA"),
        ("cns", "CÓDIGO DO CARTÓRIO/CNS"),
        ("registration", "MATRÍCULA"),
        ("reference_system", "SISTEMA DE REFERÊNCIA"),
    ):
        value = (property_metadata or {}).get(key)
        if value:
            lines.append(f"{label}: {value[:250]}")

    lines += [
        f"ÁREA TOTAL: {_br_number(sum(p.area_ha for p in parcels), 4)} ha",
        f"PERÍMETRO TOTAL: {_br_number(sum(p.perimeter for p in parcels), 2)} m",
        "",
    ]
    for parcel in parcels:
        lines.append(f"DESCRIÇÃO DO PERÍMETRO - {parcel.name}")
        initial = parcel.segments[0]
        start_alt = parcel.altitudes[0]
        altitude_clause = (
            f' e Altitude: {_br_number(start_alt, 2)} m'
            if start_alt is not None else ""
        )
        story = (
            f"Inicia-se a descrição deste perímetro no vértice {initial['start']}, "
            f"de coordenadas (Longitude: {_dms(initial['lon'], 'lon')}, "
            f"Latitude: {_dms(initial['lat'], 'lat')}{altitude_clause}); "
        )
        previous = None
        for i, segment in enumerate(parcel.segments):
            confrontant = parcel.confrontants[i].strip()
            if i == 0 or confrontant != previous:
                if i > 0:
                    story += " "
                if confrontant:
                    story += (
                        f"Linha ideal; deste, segue confrontando com {confrontant}, "
                        "com os seguintes azimutes e distâncias: "
                    )
                else:
                    story += (
                        "Linha ideal; deste, segue por trecho cujo confrontante não "
                        "foi informado, com os seguintes azimutes e distâncias: "
                    )
            next_is_start = i == len(parcel.segments) - 1
            story += (
                f"{_azimuth_minutes(segment['azimuth'])} e "
                f"{_br_number(segment['distance'], 2)} m até o vértice "
                f"{segment['end']}"
            )
            if next_is_start:
                story += ", ponto inicial da descrição deste perímetro."
            else:
                altitude = parcel.altitudes[i + 1]
                altitude_part = (
                    f" e Altitude: {_br_number(altitude, 2)} m"
                    if altitude is not None else ""
                )
                story += (
                    f", (Longitude: {_dms(segment['next_lon'], 'lon')}, "
                    f"Latitude: {_dms(segment['next_lat'], 'lat')}"
                    f"{altitude_part}); "
                )
            previous = confrontant
        lines.append(story)
        lines.append(
            f"Área desta parcela: {_br_number(parcel.area_ha, 4)} ha; "
            f"perímetro: {_br_number(parcel.perimeter, 2)} m."
        )
        lines.append("")
    if croqui:
        lines.append(
            "Coordenadas referenciadas ao SIRGAS 2000; azimutes e distâncias "
            "geodésicos calculados sobre o elipsóide GRS80. "
            "A precisão depende da fonte da geometria; a emissão não corresponde "
            "a certificação fundiária."
        )
        lines.extend(["", "OBSERVAÇÃO:", DISCLAIMER])
    person = responsible or professional.get("full_name") or "Não informado"
    lines.extend(["", "________________________________________", person])
    credentials = [
        str(professional.get(key) or "").strip()
        for key in ("profession", "specialization", "crea", "visto", "incra_code", "art")
    ]
    lines.extend(value for value in credentials if value)
    return "\n".join(lines)


def _paper_and_scale(parcels: list[Parcel], projected: list[list[tuple[float, float]]]):
    points = [point for ring in projected for point in ring]
    min_x = min(x for x, _ in points)
    max_x = max(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_y = max(y for _, y in points)
    dx = max(1.0, max_x - min_x) * 1.15
    dy = max(1.0, max_y - min_y) * 1.15
    count = sum(len(p.points) for p in parcels)
    for name, (w, h) in SIZES:
        # Reserva quadro técnico lateral de 23% da prancha e margens de gráfica.
        draw_w = w * 0.72 - 95
        draw_h = h - 180
        for denom in SCALES:
            # Um ponto tipográfico mede exatamente 1/72 polegada.
            required_x = dx * 72 / (denom * 0.0254)
            required_y = dy * 72 / (denom * 0.0254)
            if required_x <= draw_w and required_y <= draw_h:
                # A0/A1 com poucos vértices não devem ser escolhidos sem necessidade.
                if count > 180 and name in ("A4", "A3"):
                    continue
                return name, (w, h), denom, (min_x, min_y, max_x, max_y)
    raise ValueError("Extensão incompatível com escala legível em A0; divida a planta.")


def _raster_reader(raw: str | None):
    if not raw:
        return None
    data = base64.b64decode(raw, validate=True)
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("Raster excede 8 MB.")
    stream = io.BytesIO(data)
    image = Image.open(stream)
    image.verify()
    stream.seek(0)
    image = Image.open(stream).convert("RGB")
    if image.width * image.height > 25_000_000:
        raise ValueError("Raster excede 25 megapixels.")
    return ImageReader(image)


def make_joint_pdf(
    *,
    parcels: list[Parcel],
    title: str,
    owner_name: str | None,
    responsible_name: str | None,
    croqui: bool,
    raster_b64: str | None,
    raster_source: str | None,
    owner_rg: str | None = None,
    owner_cpf: str | None = None,
    property_address: str | None = None,
    plant_heading: str = "PLANTA GEORREFERENCIADA",
    memorial_heading: str = "MEMORIAL DESCRITIVO",
    professional: dict | None = None,
    qr_url: str | None = None,
) -> tuple[bytes, str, int]:
    config = load_document_template()
    professional = professional or {}
    if not raster_b64:
        raise ValueError("A planta de situação exige uma imagem raster capturada do mapa.")
    issued_at = datetime.now(ZoneInfo("America/Belem"))
    all_points = [pt for p in parcels for pt in p.points]
    center_lon = sum(x for x, _ in all_points) / len(all_points)
    center_lat = sum(y for _, y in all_points) / len(all_points)
    zone = max(1, min(60, int((center_lon + 180) // 6) + 1))
    hemisphere = "S" if center_lat < 0 else "N"
    utm = CRS.from_proj4(
        f"+proj=utm +zone={zone} {'+south' if hemisphere == 'S' else ''} "
        "+ellps=GRS80 +units=m +no_defs"
    )
    transformer = Transformer.from_crs("EPSG:4674", utm, always_xy=True)
    projected = [[transformer.transform(*pt) for pt in p.points] for p in parcels]
    page_format, (w, h), scale, limits = _paper_and_scale(parcels, projected)
    min_x, min_y, max_x, max_y = limits
    box_left, box_bottom = 42, 90
    box_width = w * 0.72 - 60
    box_height = h - 190
    # Escala física 1:n (nunca ampliar livremente para preencher a prancha).
    factor = 72 / (scale * 0.0254)
    offset_x = box_left + (box_width - (max_x - min_x) * factor) / 2
    offset_y = box_bottom + (box_height - (max_y - min_y) * factor) / 2

    def xy(x, y):
        return offset_x + (x - min_x) * factor, offset_y + (y - min_y) * factor

    raster = _raster_reader(raster_b64)
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(w, h))
    pdf.setTitle(f"{title} - Planta e Memorial")
    pdf.setLineWidth(1)
    pdf.rect(24, 24, w - 48, h - 48)
    pdf.line(w * .74, 24, w * .74, h - 24)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, h - 55, plant_heading[:110].upper())
    pdf.setFont("Helvetica", 10)
    pdf.drawString(40, h - 72, title[:100])
    pdf.setFont("Helvetica", 7)
    pdf.drawString(42, 62, f"SIRGAS 2000 / UTM {zone}{hemisphere} - Escala 1:{scale:,} - {page_format}")
    pdf.drawString(42, 49, "Área e perímetro: calculados com elipsóide GRS80; conferir precisão da origem.")
    pdf.setFont("Helvetica", 6.5)
    pdf.drawString(42, 34, str(config.get("document_footer") or "Documento técnico gerado pelo Amazônika Geoespacial.")[:100])

    if len(parcels) > 1:
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(42, h - 93, f"{len(parcels)} polígonos selecionados")
    palette = [(0.08, 0.42, 0.29), (0.14, 0.32, 0.68), (0.69, 0.32, 0.13),
              (0.52, 0.25, 0.59), (0.32, 0.45, 0.20)]
    # Grade georreferenciada UTM, com cotas em metros e espaçamento legível.
    grid_step = max(1, int(10 ** math.floor(math.log10(max(max_x-min_x,max_y-min_y,1) / 4))))
    if max(max_x - min_x, max_y - min_y) / grid_step > 9:
        grid_step *= 2
    pdf.saveState()
    pdf.setStrokeColor(colors.Color(.65, .72, .68, alpha=.45))
    pdf.setLineWidth(.35)
    pdf.setFont("Helvetica", 6)
    grid_min_x = int(math.floor(min_x / grid_step)) * grid_step
    grid_min_y = int(math.floor(min_y / grid_step)) * grid_step
    for value in range(grid_min_x, int(max_x)+grid_step+1, grid_step):
        xline, _ = xy(value, min_y)
        if box_left <= xline <= box_left+box_width:
            pdf.line(xline, box_bottom, xline, box_bottom+box_height)
            pdf.drawCentredString(xline, box_bottom-13, f"E {value:,}")
    for value in range(grid_min_y, int(max_y)+grid_step+1, grid_step):
        _, yline = xy(min_x, value)
        if box_bottom <= yline <= box_bottom+box_height:
            pdf.line(box_left, yline, box_left+box_width, yline)
            pdf.drawRightString(box_left-5, yline, f"N {value:,}")
    pdf.restoreState()

    for parcel_index, (parcel, points) in enumerate(zip(parcels, projected)):
        r, g, b = palette[parcel_index % len(palette)]
        path = pdf.beginPath()
        path.moveTo(*xy(*points[0]))
        for point in points[1:]:
            path.lineTo(*xy(*point))
        path.close()
        pdf.setFillColorRGB(r, g, b, alpha=0.09)
        pdf.setStrokeColorRGB(r, g, b)
        pdf.setLineWidth(1.8)
        pdf.drawPath(path, fill=1, stroke=1)
        # Etiquetas de vértices e segmentos com distâncias e azimutes.
        for index, (pt, vertex, segment) in enumerate(zip(points, parcel.names, parcel.segments)):
            x, y = xy(*pt)
            next_x, next_y = xy(*points[(index + 1) % len(points)])
            pdf.setFillColorRGB(1, 1, 1)
            pdf.circle(x, y, 2, fill=1, stroke=1)
            pdf.setFont("Helvetica-Bold", 6.5)
            pdf.setFillColorRGB(0.02, 0.19, 0.12)
            pdf.drawString(x + 4, y + 4, vertex[:26])
            angle = math.atan2(next_y - y, next_x - x)
            midpoint = ((x + next_x) / 2, (y + next_y) / 2)
            if math.hypot(next_x - x, next_y - y) >= 34:
                pdf.saveState()
                pdf.translate(*midpoint)
                degrees = math.degrees(angle)
                if degrees > 90 or degrees < -90:
                    degrees = (degrees + 180) % 360
                pdf.rotate(degrees)
                pdf.setFont("Helvetica", 5.8)
                pdf.drawCentredString(
                    0, 4, f"{segment['azimuth']:.2f}° / {segment['distance']:.2f}m"
                )
                pdf.restoreState()

    # Seta de norte e barra gráfica no painel cartográfico.
    nx = box_left + 20
    ny = box_bottom + box_height - 20
    pdf.setStrokeColorRGB(.09, .30, .23)
    pdf.line(nx, ny - 24, nx, ny)
    pdf.line(nx, ny, nx - 5, ny - 9)
    pdf.line(nx, ny, nx + 5, ny - 9)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawCentredString(nx, ny + 5, "N")
    bar_m = max(1, scale // 10)
    bar_pts = bar_m * factor
    pdf.setLineWidth(3)
    pdf.line(55, 78, 55 + bar_pts, 78)
    pdf.setFont("Helvetica", 7)
    pdf.drawString(55, 67, "0")
    pdf.drawRightString(55 + bar_pts, 67, f"{bar_m} m")

    right_x = w * .74 + 15
    right_w = w * .26 - 42
    logo = _logo_path(config)
    if logo:
        try:
            pdf.drawImage(ImageReader(str(logo)), right_x, h - 105,
                          width=min(right_w, 135), height=65,
                          preserveAspectRatio=True, mask="auto")
        except (OSError, ValueError):
            pass
    pdf.setFillColorRGB(0, 0, 0)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(right_x, h - 125, str(config.get("company_name") or "Amazônika")[:35])
    pdf.setFont("Helvetica", 8)
    detail = [
        f"Prancha: {page_format} / Paisagem",
        f"Escala nominal: 1:{scale:,}",
        f"Fuso: {zone}{hemisphere}",
        f"Impressão: tamanho real / 100%",
        f"Data: {date.today():%d/%m/%Y}",
        f"Interessado: {owner_name or 'Não informado'}",
        f"RG / CPF: {owner_rg or '—'} / {owner_cpf or '—'}",
        f"Endereço do imóvel: {property_address or 'Não informado'}",
        f"Técnico: {responsible_name or professional.get('full_name') or 'Não informado'}",
        f"Profissão: {professional.get('profession') or '—'}",
        f"Especialização: {professional.get('specialization') or '—'}",
        f"RG técnico: {professional.get('rg') or '—'}",
        f"CPF técnico: {professional.get('cpf') or '—'}",
        f"CREA: {professional.get('crea') or '—'}",
        f"Visto: {professional.get('visto') or '—'}",
        f"INCRA: {professional.get('incra_code') or '—'}",
        f"ART: {professional.get('art') or 'Não informada'}",
        f"Área total: {sum(p.area_ha for p in parcels):,.4f} ha",
        f"Perímetros somados: {sum(p.perimeter for p in parcels):,.3f} m",
    ]
    y = h - 145
    for item in detail:
        for line in textwrap.wrap(item, width=max(22, int(right_w / 5))):
            pdf.drawString(right_x, y, line)
            y -= 12
        y -= 2
    y -= 8
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(right_x, y, "QUADRO DE ÁREAS")
    y -= 15
    pdf.setFont("Helvetica", 7)
    for parcel in parcels[:50]:
        for line in textwrap.wrap(f"{parcel.name}: {parcel.area_ha:.4f} ha", width=max(26, int(right_w / 4))):
            if y < 310: break
            pdf.drawString(right_x, y, line)
            y -= 11

    # Raster de situação: fornecido pelo operador com fonte identificada.
    if raster is not None:
        raster_y = 128
        raster_h = min(h * .22, max(65, y - raster_y - 18))
        if raster_h > 45:
            pdf.setFont("Helvetica-Bold", 8)
            pdf.drawString(right_x, raster_y + raster_h + 8, "PLANTA DE SITUAÇÃO (RASTER)")
            pdf.drawImage(raster, right_x, raster_y, width=right_w,
                          height=raster_h, preserveAspectRatio=True, anchor="c")
            pdf.setFont("Helvetica", 6)
            pdf.drawString(right_x, raster_y - 9, (raster_source or "Imagem fornecida pelo operador")[:52])
    else:
        raise ValueError("A imagem raster obrigatória não pôde ser inserida na prancha.")

    if croqui:
        pdf.saveState()
        pdf.translate(w - 31, 35)
        pdf.rotate(90)
        pdf.setFillColorRGB(.55, .15, .12)
        pdf.setFont("Helvetica-Bold", 6)
        pdf.drawString(0, 0, DISCLAIMER[:175])
        pdf.restoreState()

    # Rodapé e QR do documento ficam na coluna técnica e referenciam
    # uma cópia preservada no armazenamento autenticado.
    pdf.saveState()
    pdf.setFont("Helvetica", 6.5)
    issued = issued_at.strftime("%d/%m/%Y %H:%M:%S (America/Belem)")
    pdf.drawString(right_x, 37, f"Emissão: {issued}")
    if qr_url:
        import qrcode
        qrcode_png = io.BytesIO()
        qrcode.make(qr_url, box_size=4, border=1).save(qrcode_png, format="PNG")
        qrcode_png.seek(0)
        pdf.drawImage(ImageReader(qrcode_png), right_x, 47, width=57, height=57)
        pdf.drawString(right_x + 62, 51, "QR: acesso autenticado ao PDF")
    pdf.restoreState()

    # Quadro de coordenadas e segmentos em folhas suplementares
    # para garantir legibilidade em impressão de gráfica.
    pdf.showPage()
    pdf.setPageSize(landscape(A3))
    tw, th = landscape(A3)
    all_rows = []
    for parcel in parcels:
        for j, row in enumerate(parcel.segments):
            xx, yy = transformer.transform(row["lon"], row["lat"])
            altitude = parcel.altitudes[j]
            all_rows.append((
                parcel.name, row["start"], _dms(row["lat"], "lat"),
                _dms(row["lon"], "lon"), f"{xx:.3f}", f"{yy:.3f}",
                f"{altitude:.2f}" if altitude is not None else "—",
                parcel.confrontants[j] or "Não informado",
                f"{row['azimuth']:.4f}°", f"{row['distance']:.3f}",
            ))
    headers = ["Área", "Vértice", "Latitude", "Longitude", "E (m)", "N (m)",
               "Cota", "Confrontante", "Azimute", "Dist. (m)"]
    x_positions = [28, 145, 226, 330, 442, 538, 630, 682, 970, 1070]
    table_y = th - 78

    def table_header():
        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(30, th - 40, "QUADRO DE COORDENADAS E SEGMENTOS")
        pdf.setFont("Helvetica", 8)
        pdf.drawString(30, th - 55, f"SIRGAS2000 / UTM {zone}{hemisphere} - {title[:90]}")
        pdf.setFillColorRGB(.89, .94, .91)
        pdf.rect(24, table_y - 5, tw - 48, 19, fill=1, stroke=0)
        pdf.setFillColorRGB(.06, .2, .14)
        pdf.setFont("Helvetica-Bold", 7)
        for col, xpos in zip(headers, x_positions):
            pdf.drawString(xpos, table_y, col)

    table_header()
    ytable = table_y - 18
    for row in all_rows:
        if ytable < 60:
            pdf.showPage()
            pdf.setPageSize(landscape(A3))
            table_header()
            ytable = table_y - 18
        pdf.setFont("Helvetica", 6.5)
        pdf.setFillColorRGB(0, 0, 0)
        for value, xpos, max_chars in zip(row, x_positions,
                                          [22, 16, 19, 20, 18, 18, 9, 43, 16, 15]):
            pdf.drawString(xpos, ytable, str(value)[:max_chars])
        ytable -= 12

    # Páginas de memorial - tabela com todas as geometrias e segmentos.
    memorial = build_joint_memorial(
        parcels, title=title, owner=owner_name, responsible=responsible_name, croqui=croqui,
        owner_rg=owner_rg, owner_cpf=owner_cpf, property_address=property_address,
        memorial_heading=memorial_heading, professional=professional,
    )
    pdf.showPage()
    pdf.setPageSize(A4)
    mw, mh = A4
    text_x = 44
    y = mh - 50
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(text_x, y, memorial_heading[:75].upper())
    y -= 22
    pdf.setFont("Helvetica", 9)
    for paragraph in memorial.splitlines():
        for line in textwrap.wrap(paragraph, width=98, break_long_words=False) or [""]:
            if y < 85:
                pdf.setFont("Helvetica", 6.5)
                pdf.drawCentredString(mw / 2, 28, str(config.get("document_footer") or "")[:100])
                pdf.showPage()
                pdf.setPageSize(A4)
                y = mh - 48
                pdf.setFont("Helvetica", 9)
            pdf.drawString(text_x, y, line)
            y -= 13
        y -= 5
    pdf.setFont("Helvetica", 7)
    pdf.drawCentredString(mw / 2, 28, str(config.get("document_footer") or "")[:100])
    pdf.setFont("Helvetica", 6.5)
    pdf.drawRightString(mw - 30, 18, f"Emitido {issued_at:%d/%m/%Y %H:%M:%S} - Horário de Belém")
    pdf.save()
    return buffer.getvalue(), page_format, scale
