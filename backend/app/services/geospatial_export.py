from __future__ import annotations

import io
import re
import tempfile
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import geopandas as gpd
from pyproj import CRS, Transformer
from shapely import force_2d
from shapely.geometry import MultiPolygon, Point, Polygon, shape


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-")[:65] or "poligono"


def _geometry(value: dict) -> Polygon:
    # Polígonos importados (KML/SIGEF) ou com altitude informada chegam com
    # coordenadas XYZ; a exportação planimétrica usa somente X/Y.
    geometry = force_2d(shape(value))
    if isinstance(geometry, MultiPolygon) and len(geometry.geoms) == 1:
        geometry = geometry.geoms[0]
    if not isinstance(geometry, Polygon) or geometry.is_empty or not geometry.is_valid:
        raise ValueError("A exportação individual exige um polígono válido. Selecione uma área por vez.")
    if len(geometry.exterior.coords) < 4:
        raise ValueError("O polígono precisa ter pelo menos três vértices.")
    return geometry


def _utm(geometry: Polygon, zone: int | None, hemisphere: str | None):
    centroid = geometry.centroid
    chosen_zone = zone or max(1, min(60, int((centroid.x + 180) // 6) + 1))
    if not 1 <= chosen_zone <= 60:
        raise ValueError("Fuso UTM inválido (1 a 60).")
    direction = (hemisphere or ("S" if centroid.y < 0 else "N")).upper()
    if direction not in {"N", "S"}:
        raise ValueError("Hemisfério UTM deve ser N ou S.")
    crs = CRS.from_proj4(
        f"+proj=utm +zone={chosen_zone} {'+south' if direction == 'S' else ''} "
        "+ellps=GRS80 +units=m +no_defs"
    )
    transformer = Transformer.from_crs("EPSG:4674", crs, always_xy=True)
    return chosen_zone, direction, crs, transformer


def _names(geometry: Polygon, names: list[str] | None) -> list[str]:
    count = len(geometry.exterior.coords) - 1
    if names is not None and len(names) != count:
        raise ValueError("A quantidade de códigos precisa corresponder aos vértices.")
    values = [str(item).strip() for item in names] if names is not None else [
        f"V{index + 1:02d}" for index in range(count)
    ]
    if any(not name or len(name) > 50 for name in values) or len(set(values)) != len(values):
        raise ValueError("Os códigos dos vértices devem ser únicos, não vazios e ter até 50 caracteres.")
    return values


def export_polygon(
    *,
    geometry: dict,
    filename: str,
    format: str,
    names: list[str] | None = None,
    utm_zone: int | None = None,
    hemisphere: str | None = None,
) -> tuple[bytes, str, str]:
    polygon = _geometry(geometry)
    codes = _names(polygon, names)
    zone, direction, crs, transform = _utm(polygon, utm_zone, hemisphere)
    stem = _slug(filename)
    coordinates = list(polygon.exterior.coords)[:-1]
    rows = [
        (code, *transform.transform(lon, lat))
        for code, (lon, lat) in zip(codes, coordinates)
    ]
    txt = "codigo;X;Y\n" + "\n".join(
        f"{code};{easting:.3f};{northing:.3f}" for code, easting, northing in rows
    ) + "\n"

    if format == "txt":
        return txt.encode("utf-8-sig"), f"{stem}-utm-{zone}{direction}.txt", "text/plain; charset=utf-8"

    if format == "kml":
        # KML coordinates are WGS84 longitude, latitude order; SIRGAS2000 input
        # is transformed to EPSG:4326 before serialization.
        to_wgs84 = Transformer.from_crs("EPSG:4674", "EPSG:4326", always_xy=True)
        ring = [to_wgs84.transform(lon, lat) for lon, lat in polygon.exterior.coords]
        rings = " ".join(f"{lon:.9f},{lat:.9f},0" for lon, lat in ring)
        points = "".join(
            "<Placemark><name>" + escape(code) + "</name><Point><coordinates>"
            + f"{lon:.9f},{lat:.9f},0" + "</coordinates></Point></Placemark>"
            for code, (lon, lat) in zip(codes, [to_wgs84.transform(*point) for point in coordinates])
        )
        kml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
            f"<name>{escape(filename)}</name><description>SIRGAS2000; UTM {zone}{direction}</description>"
            f"<Placemark><name>{escape(filename)}</name><Polygon><outerBoundaryIs>"
            f"<LinearRing><coordinates>{rings}</coordinates></LinearRing>"
            f"</outerBoundaryIs></Polygon></Placemark>{points}</Document></kml>"
        )
        return kml.encode("utf-8"), f"{stem}.kml", "application/vnd.google-earth.kml+xml"

    if format != "shp":
        raise ValueError("Formato inválido. Use txt, kml ou shp.")

    with tempfile.TemporaryDirectory(prefix="amazonika-export-") as directory:
        root = Path(directory)
        polygon_gdf = gpd.GeoDataFrame(
            [{"NOME": filename[:80], "FUSO": zone, "HEMIS": direction}],
            geometry=[polygon],
            crs="EPSG:4674",
        )
        points_gdf = gpd.GeoDataFrame(
            [
                {"CODIGO": code[:50], "X_UTM": round(x, 3), "Y_UTM": round(y, 3)}
                for code, x, y in rows
            ],
            geometry=[Point(*point) for point in coordinates],
            crs="EPSG:4674",
        )
        polygon_gdf.to_file(root / "poligono.shp", driver="ESRI Shapefile", engine="pyogrio")
        points_gdf.to_file(root / "vertices.shp", driver="ESRI Shapefile", engine="pyogrio")
        (root / "coordenadas_utm.txt").write_text(txt, encoding="utf-8-sig")
        (root / "referencia.txt").write_text(
            f"SIRGAS2000 / UTM fuso {zone}{direction} (GRS80)\n"
            "X=Este (m); Y=Norte (m).\n"
            "Camadas poligono e vertices entregues em EPSG:4674.\n",
            encoding="utf-8",
        )
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.iterdir()):
                if path.is_file():
                    archive.write(path, path.name)
        return output.getvalue(), f"{stem}-shapefile.zip", "application/zip"
