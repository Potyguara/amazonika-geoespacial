"""Generic thematic cartography: user-provided vector geometries and standardized PDF."""
import io
import math
from collections import Counter
from dataclasses import dataclass

from pyproj import CRS, Transformer
from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen.canvas import Canvas
from shapely.geometry import shape, Polygon, MultiPolygon, Point, MultiPoint, LineString, MultiLineString, GeometryCollection
from shapely.ops import transform as shapely_transform

TEMPLATES = [
    ("situacao", "Mapa de Situação"),
    ("uso-solo", "Uso e Ocupação do Solo"),
    ("acessos", "Acessos da Propriedade"),
    ("ucs", "Localização em Relação às Unidades de Conservação"),
    ("flota", "FLOTA e Zona de Amortecimento"),
    ("geologia", "Unidades Geológicas Ambientais"),
    ("geomorfologia", "Unidades Geomorfológicas"),
    ("pedologia", "Solos / Pedologia"),
    ("hidrografia", "Malha Hidrográfica"),
    ("vegetacao", "Caracterização da Vegetação"),
    ("personalizado", "Mapa Temático Personalizado"),
]
PALETTE = ["#73c6ad", "#e7b75a", "#8bb4df", "#ce94c4", "#9dc464", "#e59c8b", "#a6a0d6", "#7eb8b2"]


@dataclass
class Layer:
    name: str
    source: str
    geometry: object
    color: str
    role: str


def _color(value: str):
    raw = str(value).strip().lstrip("#")
    if len(raw) != 6 or any(c not in "0123456789abcdefABCDEF" for c in raw):
        raise ValueError("Cor hexadecimal inválida.")
    return colors.HexColor("#" + raw)


def _projected(layers):
    property_geoms = [l.geometry for l in layers if l.role == "property"]
    if not property_geoms:
        raise ValueError("Inclua a geometria da propriedade.")
    prop = property_geoms[0]
    lon, lat = prop.centroid.x, prop.centroid.y
    zone = max(1, min(60, int((lon + 180) / 6) + 1))
    epsg = (31976 if lat >= 0 else 31982) if zone == 22 else (32700 if lat < 0 else 32600) + zone
    destination = CRS.from_epsg(epsg)
    tf = Transformer.from_crs("EPSG:4674", destination, always_xy=True)
    projected = [shapely_transform(tf.transform, l.geometry) for l in layers]
    return projected, epsg


def _draw_geometry(pdf, geometry, xy, stroke, fill, property_outline=False, property_fill=False):
    if geometry.is_empty:
        return
    if isinstance(geometry, (MultiPolygon, MultiLineString, MultiPoint, GeometryCollection)):
        for g in geometry.geoms:
            _draw_geometry(pdf, g, xy, stroke, fill, property_outline, property_fill)
    elif isinstance(geometry, Polygon):
        path = pdf.beginPath()
        for ring_index, ring in enumerate([geometry.exterior, *geometry.interiors]):
            points = list(ring.coords)
            if not points:
                continue
            path.moveTo(*xy(points[0][0], points[0][1]))
            for p in points[1:]:
                path.lineTo(*xy(p[0], p[1]))
            path.close()
        pdf.setStrokeColor(stroke)
        pdf.setLineWidth(2.6 if property_outline else 0.55)
        if property_outline:
            pdf.setFillColor(fill)
            pdf.drawPath(path, stroke=1, fill=int(property_fill))
        else:
            pdf.setFillColor(fill)
            pdf.drawPath(path, stroke=1, fill=1, fillMode=0)
    elif isinstance(geometry, LineString):
        points = list(geometry.coords)
        if not points:
            return
        path = pdf.beginPath()
        path.moveTo(*xy(points[0][0], points[0][1]))
        for p in points[1:]:
            path.lineTo(*xy(p[0], p[1]))
        pdf.setStrokeColor(stroke)
        pdf.setLineWidth(1.3)
        pdf.drawPath(path, stroke=1)
    elif isinstance(geometry, Point):
        pdf.setFillColor(fill)
        pdf.setStrokeColor(stroke)
        pdf.circle(*xy(geometry.x, geometry.y), 3, stroke=1, fill=1)


def category_shade(hex_color: str, index: int, count: int) -> str:
    """Distinct categorical variants based on a user-approved theme hue."""
    import colorsys
    _color(hex_color)
    if count <= 1:
        return hex_color
    raw = hex_color.lstrip("#")
    r, g, b = [int(raw[i:i+2], 16) / 255 for i in (0, 2, 4)]
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    hue = (hue + ((index * 0.61803398875) % 1) * .28) % 1
    light = min(.76, max(.37, .43 + (index % 4) * .09))
    sat = max(.38, min(.78, sat))
    rr, gg, bb = colorsys.hls_to_rgb(hue, light, sat)
    return "#" + "".join(f"{round(v*255):02x}" for v in (rr, gg, bb))


def render_thematic_pdf(title, subtitle, layers, source_text, include_branding=False, style=None):
    style = style or {}
    mode = style.get("mode", "minimalista")
    grid_mode = style.get("grid", "border")
    property_mode = style.get("property", "outline")
    context = style.get("context", "balanced")
    explicit_scale = style.get("scale")
    buffer_m = style.get("buffer_m")
    if mode not in ("minimalista", "tecnico", "analitico"):
        raise ValueError("Perfil cartográfico inválido.")
    if grid_mode not in ("off", "border", "subtle", "full"):
        raise ValueError("Grade inválida.")
    if property_mode not in ("outline", "fill", "transparent"):
        raise ValueError("Estilo do imóvel inválido.")
    if context not in ("close", "balanced", "regional"):
        raise ValueError("Enquadramento inválido.")
    if explicit_scale is not None and (not isinstance(explicit_scale, (float,int)) or not 1000 <= explicit_scale <= 5000000):
        raise ValueError("Escala fora do intervalo permitido.")

    if not layers or len(layers) > 60:
        raise ValueError("Informe de 1 a 60 camadas.")
    projected, epsg = _projected(layers)
    props = [g for g, l in zip(projected, layers) if l.role == "property"]
    focus = props[0]
    minx, miny, maxx, maxy = focus.bounds
    span = max(maxx - minx, maxy - miny, 200)
    margin = float(buffer_m) if buffer_m is not None else span * {"close":.12,"balanced":.26,"regional":.60}[context]
    if not math.isfinite(margin) or margin < 0 or margin > 1000000:
        raise ValueError("Margem inválida.")
    minx -= margin; maxx += margin; miny -= margin; maxy += margin
    width_m, height_m = maxx - minx, maxy - miny
    page_w, page_h = landscape(A3)
    map_left, map_bottom, map_w, map_h = 40, 105, page_w * .76 - 50, page_h - 190
    raw_factor = min(map_w / width_m, map_h / height_m)
    raw_denominator = 72 / (raw_factor * .0254)
    scales = [1000,2500,5000,10000,25000,50000,100000,250000,500000,1000000,2500000,5000000]
    denominator = float(explicit_scale) if explicit_scale else next((v for v in scales if v >= raw_denominator), 5000000)
    if denominator < raw_denominator:
        raise ValueError("Escala manual não comporta a área no papel A3.")
    scale_factor = 72 / (denominator * .0254)
    canvas_w, canvas_h = width_m * scale_factor, height_m * scale_factor
    left = map_left + (map_w - canvas_w) / 2
    bottom = map_bottom + (map_h - canvas_h) / 2
    def xy(x, y):
        return left + (x-minx)*scale_factor, bottom+(y-miny)*scale_factor
    buffer = io.BytesIO()
    pdf = Canvas(buffer, pagesize=(page_w,page_h))
    pdf.setTitle(title)
    pdf.setFillColor(colors.HexColor("#123e30"))
    pdf.setStrokeColor(colors.HexColor("#b6c8bc"))
    pdf.setLineWidth(.65)
    pdf.roundRect(24,22,page_w-48,page_h-44,7,stroke=1,fill=0)
    pdf.setFont("Helvetica-Bold",18)
    pdf.drawCentredString(page_w/2,page_h-52,title[:76].upper())
    if subtitle:
        pdf.setFont("Helvetica",9)
        pdf.drawCentredString(page_w/2,page_h-69,subtitle[:110])
    pdf.setStrokeColor(colors.HexColor("#637f78"))
    pdf.setLineWidth(.7)
    pdf.rect(map_left,map_bottom,map_w,map_h)
    # Render only clipped geometries, in source order, with property always last.
    pdf.saveState()
    clip_path=pdf.beginPath()
    clip_path.rect(map_left,map_bottom,map_w,map_h)
    pdf.clipPath(clip_path,stroke=0)
    step = max(10,10 ** math.floor(math.log10(max(width_m,height_m)/5)))
    if grid_mode in ("subtle", "full"):
        pdf.setLineWidth(.25 if grid_mode == "subtle" else .5)
        pdf.setStrokeColor(colors.HexColor("#e6ece8" if grid_mode == "subtle" else "#b8c8be"))
        for i in range(int(math.floor(minx/step)),int(math.ceil(maxx/step))+1):
            px = xy(i*step,miny)[0]
            pdf.line(px,map_bottom,px,map_bottom+map_h)
        for i in range(int(math.floor(miny/step)),int(math.ceil(maxy/step))+1):
            py = xy(minx,i*step)[1]
            pdf.line(map_left,py,map_left+map_w,py)
    # White opaque background prevents the reference grid from crossing polygons.
    # Draw polygons first, then hydrology/roads, then the property perimeter.
    ordered_layers = sorted(zip(layers,projected), key=lambda pair: (
        2 if pair[0].role=="property" else
        0 if pair[1].geom_type in ("Polygon","MultiPolygon") else
        1
    ))
    for role in ("theme", "property"):
        for layer, geom in ordered_layers:
            if layer.role != role:
                continue
            c=_color(layer.color)
            if role == "property" and property_mode == "transparent":
                pdf.saveState()
                pdf.setFillAlpha(.15)
                _draw_geometry(pdf,geom,xy,c,c,property_outline=True,property_fill=True)
                pdf.restoreState()
                _draw_geometry(pdf,geom,xy,c,c,property_outline=True)
            else:
                _draw_geometry(pdf,geom,xy,c,c,property_outline=role=="property",
                               property_fill=role=="property" and property_mode=="fill")
    pdf.restoreState()
    pdf.setFont("Helvetica",7)
    pdf.setFillColor(colors.HexColor("#285c4a"))
    for i in (range(int(math.floor(minx/step)),int(math.ceil(maxx/step))+1) if grid_mode != "off" else []):
        x=i*step; p=xy(x,miny)[0]
        if map_left+10 <= p <= map_left+map_w-10:
            pdf.drawCentredString(p,map_bottom-10,f"{x:,.0f}")
    for i in (range(int(math.floor(miny/step)),int(math.ceil(maxy/step))+1) if grid_mode != "off" else []):
        y=i*step; p=xy(minx,y)[1]
        if map_bottom+10 <= p <= map_bottom+map_h-10:
            pdf.drawRightString(map_left-4,p,f"{y:,.0f}")
    panel_x=map_left+map_w+20
    panel_w=page_w-panel_x-40
    pdf.setStrokeColor(colors.HexColor("#d4dfd9"))
    pdf.roundRect(panel_x-9,230,panel_w+8,page_h-326,6,stroke=1,fill=0)
    pdf.setFillColor(colors.HexColor("#194c39"))
    pdf.setFont("Helvetica-Bold",11); pdf.drawString(panel_x,page_h-112,"LEGENDA")
    pdf.setStrokeColor(colors.HexColor("#b7c8bf"))
    pdf.line(panel_x,page_h-120,panel_x+panel_w-5,page_h-120)
    y=page_h-142
    for layer in layers:
        c=_color(layer.color)
        pdf.setStrokeColor(c); pdf.setFillColor(c)
        g=layer.geometry
        if layer.role=="property":
            pdf.setLineWidth(2)
            pdf.rect(panel_x,y-3,15,10,stroke=1,fill=int(property_mode=="fill"))
        elif g.geom_type in ("LineString","MultiLineString"):
            pdf.setLineWidth(2)
            pdf.line(panel_x,y+2,panel_x+15,y+2)
        elif g.geom_type in ("Point","MultiPoint"):
            pdf.circle(panel_x+7,y+2,3.5,stroke=1,fill=1)
        else:
            pdf.rect(panel_x,y-3,15,10,stroke=1,fill=1)
        pdf.setFillColor(colors.black);pdf.setFont("Helvetica",8)
        from textwrap import wrap
        label=layer.name.split(": ",1)[1] if ": " in layer.name else layer.name
        lines=wrap(label,26) or [label]
        for index,line in enumerate(lines[:3]):
            pdf.drawString(panel_x+20,y-9*index,line)
        y-=max(22,len(lines[:3])*10+8)
        if y<250:
            pdf.setFont("Helvetica-Oblique",7)
            pdf.drawString(panel_x,y,"Legenda extensa: reduza as camadas.")
            break
    pdf.setFont("Helvetica-Bold",9)
    pdf.drawString(panel_x,192,"REFERÊNCIA CARTOGRÁFICA")
    pdf.setFont("Helvetica",8)
    for i,line in enumerate(["Datum: SIRGAS 2000","Projeção: UTM","SRC de trabalho: EPSG:"+str(epsg),"Unidade: metros"]):
        pdf.drawString(panel_x,177-i*13,line)
    pdf.setFont("Helvetica-Bold",8);pdf.drawString(panel_x,117,"FONTES")
    from textwrap import wrap
    sources=source_text or "; ".join(dict.fromkeys(l.source for l in layers))
    for i,line in enumerate(wrap(sources,53)[:4]):
        pdf.setFont("Helvetica",6.7);pdf.drawString(panel_x,104-i*10,line)
    # Scale and north are computed for the map's physical print dimensions.
    scale=denominator
    pdf.setFont("Helvetica-Bold",9)
    pdf.drawString(42,75,f"ESCALA 1:{scale:,.0f}".replace(",","." ))
    bar_length_m=max(10,round(85/scale_factor/10)*10)
    bar_pts=bar_length_m*scale_factor
    pdf.setStrokeColor(colors.black);pdf.setLineWidth(3)
    pdf.line(220,75,220+bar_pts,75)
    pdf.setFont("Helvetica",7);pdf.drawString(220,39,"0")
    pdf.drawRightString(220+bar_pts,62,f"{bar_length_m:,} m")
    pdf.setFont("Helvetica-Bold",15);pdf.drawCentredString(panel_x+panel_w/2,254,"N")
    nx=panel_x+panel_w/2
    pdf.line(nx,212,nx,243)
    pdf.line(nx,243,nx-8,227)
    pdf.line(nx,243,nx+8,227)
    if include_branding:
        pdf.setFont("Helvetica",7);pdf.drawString(42,23,"AMAZÔNIKA GEOESPACIAL  |  MAPAS TEMÁTICOS")
    pdf.showPage();pdf.save()
    return buffer.getvalue()
