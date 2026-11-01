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


def _draw_geometry(pdf, geometry, xy, stroke, fill, property_outline=False):
    if geometry.is_empty:
        return
    if isinstance(geometry, (MultiPolygon, MultiLineString, MultiPoint, GeometryCollection)):
        for g in geometry.geoms:
            _draw_geometry(pdf, g, xy, stroke, fill, property_outline)
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
            pdf.drawPath(path, stroke=1, fill=0)
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


def render_thematic_pdf(title, subtitle, layers, source_text, include_branding=False):
    if not layers or len(layers) > 60:
        raise ValueError("Informe de 1 a 60 camadas.")
    projected, epsg = _projected(layers)
    props = [g for g, l in zip(projected, layers) if l.role == "property"]
    focus = props[0]
    minx, miny, maxx, maxy = focus.bounds
    span = max(maxx - minx, maxy - miny, 200)
    margin = span * 0.38
    minx -= margin; maxx += margin; miny -= margin; maxy += margin
    width_m, height_m = maxx - minx, maxy - miny
    page_w, page_h = landscape(A3)
    map_left, map_bottom, map_w, map_h = 42, 82, page_w * .67 - 54, page_h - 138
    scale_factor = min(map_w / width_m, map_h / height_m)
    canvas_w, canvas_h = width_m * scale_factor, height_m * scale_factor
    left = map_left + (map_w - canvas_w) / 2
    bottom = map_bottom + (map_h - canvas_h) / 2
    def xy(x, y):
        return left + (x-minx)*scale_factor, bottom+(y-miny)*scale_factor
    buffer = io.BytesIO()
    pdf = Canvas(buffer, pagesize=(page_w,page_h))
    pdf.setTitle(title)
    pdf.setFillColor(colors.HexColor("#123e30"))
    pdf.setFont("Helvetica-Bold",16)
    pdf.drawString(42,page_h-43,title[:83].upper())
    pdf.setFont("Helvetica",9)
    pdf.drawString(42,page_h-58,subtitle[:110])
    pdf.setStrokeColor(colors.HexColor("#678d82"))
    pdf.rect(map_left,map_bottom,map_w,map_h)
    # Render only clipped geometries, in source order, with property always last.
    pdf.saveState()
    clip_path=pdf.beginPath()
    clip_path.rect(map_left,map_bottom,map_w,map_h)
    pdf.clipPath(clip_path,stroke=0)
    step = 10 ** math.floor(math.log10(max(width_m,height_m)/5))
    step = max(10,step)
    pdf.setLineWidth(.3)
    pdf.setStrokeColor(colors.HexColor("#d6dfdb"))
    for i in range(int(math.floor(minx/step)),int(math.ceil(maxx/step))+1):
        x=i*step
        pdf.line(xy(x,miny)[0],map_bottom,xy(x,miny)[0],map_bottom+map_h)
    for i in range(int(math.floor(miny/step)),int(math.ceil(maxy/step))+1):
        y=i*step
        pdf.line(map_left,xy(minx,y)[1],map_left+map_w,xy(minx,y)[1])
    # Layers are thematic overlays; the property outline always appears on top.
    for role in ("theme", "property"):
        for layer, geom in zip(layers,projected):
            if layer.role != role:
                continue
            c=_color(layer.color)
            _draw_geometry(pdf,geom,xy,c,c,property_outline=role=="property")
    pdf.restoreState()
    pdf.setFont("Helvetica",7)
    pdf.setFillColor(colors.HexColor("#285c4a"))
    for i in range(int(math.floor(minx/step)),int(math.ceil(maxx/step))+1):
        x=i*step; p=xy(x,miny)[0]
        if map_left+10 <= p <= map_left+map_w-10:
            pdf.drawCentredString(p,map_bottom-10,f"{x:,.0f}")
    for i in range(int(math.floor(miny/step)),int(math.ceil(maxy/step))+1):
        y=i*step; p=xy(minx,y)[1]
        if map_bottom+10 <= p <= map_bottom+map_h-10:
            pdf.drawRightString(map_left-4,p,f"{y:,.0f}")
    panel_x=map_left+map_w+20
    pdf.setFont("Helvetica-Bold",11); pdf.drawString(panel_x,page_h-92,"LEGENDA")
    y=page_h-115
    for layer in layers:
        c=_color(layer.color)
        pdf.setStrokeColor(c); pdf.setFillColor(c)
        if layer.role=="property":
            pdf.rect(panel_x,y-3,13,9,stroke=1,fill=0)
        else: pdf.rect(panel_x,y-3,13,9,stroke=1,fill=1)
        pdf.setFillColor(colors.black);pdf.setFont("Helvetica",8)
        from textwrap import wrap
        lines=wrap(layer.name,36) or [layer.name]
        for index,line in enumerate(lines[:3]):
            pdf.drawString(panel_x+20,y-9*index,line)
        y-=max(22,len(lines[:3])*10+8)
        if y<210:
            pdf.setFont("Helvetica-Oblique",7)
            pdf.drawString(panel_x,y,"Legenda extensa: reduza as camadas.")
            break
    pdf.setFont("Helvetica-Bold",9)
    pdf.drawString(panel_x,180,"INFORMAÇÕES CARTOGRÁFICAS")
    pdf.setFont("Helvetica",8)
    for i,line in enumerate(["Datum: SIRGAS 2000","Projeção: UTM","SRC de trabalho: EPSG:"+str(epsg),"Unidade: metros"]):
        pdf.drawString(panel_x,163-i*13,line)
    pdf.setFont("Helvetica-Bold",8);pdf.drawString(panel_x,98,"FONTES")
    from textwrap import wrap
    sources=source_text or "; ".join(dict.fromkeys(l.source for l in layers))
    for i,line in enumerate(wrap(sources,53)[:4]):
        pdf.setFont("Helvetica",6.7);pdf.drawString(panel_x,85-i*10,line)
    # Scale and north are computed for the map's physical print dimensions.
    scale=72/(scale_factor*.0254)
    pdf.setFont("Helvetica-Bold",9)
    pdf.drawString(42,53,f"ESCALA 1:{scale:,.0f}".replace(",","." ))
    bar_length_m=max(10,round(85/scale_factor/10)*10)
    bar_pts=bar_length_m*scale_factor
    pdf.setStrokeColor(colors.black);pdf.setLineWidth(3)
    pdf.line(220,51,220+bar_pts,51)
    pdf.setFont("Helvetica",7);pdf.drawString(220,39,"0")
    pdf.drawRightString(220+bar_pts,39,f"{bar_length_m:,} m")
    pdf.setFont("Helvetica-Bold",15);pdf.drawCentredString(map_left+map_w-18,map_bottom+map_h-22,"N")
    pdf.line(map_left+map_w-18,map_bottom+map_h-50,map_left+map_w-18,map_bottom+map_h-30)
    pdf.line(map_left+map_w-18,map_bottom+map_h-30,map_left+map_w-24,map_bottom+map_h-41)
    pdf.line(map_left+map_w-18,map_bottom+map_h-30,map_left+map_w-12,map_bottom+map_h-41)
    if include_branding:
        pdf.setFont("Helvetica",7);pdf.drawString(42,23,"AMAZÔNIKA GEOESPACIAL  |  MAPAS TEMÁTICOS")
    pdf.showPage();pdf.save()
    return buffer.getvalue()
