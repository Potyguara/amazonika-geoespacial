"""Exportação de parcelas selecionadas no mapa (qualquer base) em SHP ou KML.

Cada parcela chega em GeoJSON (EPSG:4326, como o mapa as entrega) com o nome,
a camada de origem e os atributos consultados pelo Identificar. O resultado
é um único arquivo com todas as parcelas, preservando os atributos.
"""
from __future__ import annotations

import csv
import io
import re
import tempfile
import unicodedata
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import geopandas as gpd
from pyproj import Geod
from shapely import force_2d, make_valid
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry

MAX_PARCELS = 500
_GEOD = Geod(ellps="GRS80")
_FIXED = ("NOME", "CAMADA", "AREA_HA")


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-")[:65] or "parcelas"


def _ascii(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")


def _polygonal(value: dict) -> Polygon | MultiPolygon:
    geometry: BaseGeometry = force_2d(shape(value))
    if geometry.is_empty:
        raise ValueError("Parcela sem geometria.")
    if not geometry.is_valid:
        geometry = make_valid(geometry)
    if geometry.geom_type == "GeometryCollection":
        parts = [g for g in geometry.geoms if isinstance(g, (Polygon, MultiPolygon))]
        polys = [p for g in parts for p in (g.geoms if isinstance(g, MultiPolygon) else [g])]
        geometry = MultiPolygon(polys) if len(polys) > 1 else (polys[0] if polys else geometry)
    if not isinstance(geometry, (Polygon, MultiPolygon)):
        raise ValueError("Somente parcelas poligonais podem ser exportadas.")
    return geometry


def _area_ha(geometry: Polygon | MultiPolygon) -> float:
    return abs(_GEOD.geometry_area_perimeter(geometry)[0]) / 10000


def _text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _field_names(keys: list[str]) -> dict[str, str]:
    """Nomes de campo DBF: até 10 caracteres ASCII, únicos e sem colidir com os fixos."""
    used = set(_FIXED)
    mapping: dict[str, str] = {}
    for key in keys:
        base = re.sub(r"[^A-Za-z0-9_]+", "_", _ascii(key)).strip("_").upper() or "CAMPO"
        candidate = base[:10]
        counter = 1
        while candidate in used:
            suffix = str(counter)
            candidate = base[: 10 - len(suffix)] + suffix
            counter += 1
        used.add(candidate)
        mapping[key] = candidate
    return mapping


def _prepare(parcels: list[dict]) -> list[dict]:
    if not parcels:
        raise ValueError("Selecione ao menos uma parcela para exportar.")
    if len(parcels) > MAX_PARCELS:
        raise ValueError(f"Exporte no máximo {MAX_PARCELS} parcelas por vez.")
    prepared = []
    for index, parcel in enumerate(parcels, start=1):
        name = _text(parcel.get("name")) or f"Parcela {index}"
        try:
            geometry = _polygonal(parcel.get("geometry") or {})
        except Exception as exc:  # shapely lança erros variados para GeoJSON inválido
            raise ValueError(f"{name}: {exc}") from exc
        properties = {
            _text(key): _text(value)
            for key, value in (parcel.get("properties") or {}).items()
            if _text(key)
        }
        prepared.append({
            "name": name,
            "layer": _text(parcel.get("layer")),
            "geometry": geometry,
            "area_ha": _area_ha(geometry),
            "properties": properties,
        })
    return prepared


def _kml_polygon(polygon: Polygon) -> str:
    def ring(coords) -> str:
        return " ".join(f"{x:.9f},{y:.9f},0" for x, y in coords)

    inner = "".join(
        f"<innerBoundaryIs><LinearRing><coordinates>{ring(interior.coords)}"
        "</coordinates></LinearRing></innerBoundaryIs>"
        for interior in polygon.interiors
    )
    return (
        f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{ring(polygon.exterior.coords)}"
        f"</coordinates></LinearRing></outerBoundaryIs>{inner}</Polygon>"
    )


def _kml(prepared: list[dict], title: str) -> bytes:
    placemarks = []
    for parcel in prepared:
        geometry = parcel["geometry"]
        polygons = list(geometry.geoms) if isinstance(geometry, MultiPolygon) else [geometry]
        body = "".join(_kml_polygon(p) for p in polygons)
        if len(polygons) > 1:
            body = f"<MultiGeometry>{body}</MultiGeometry>"
        data = {"Camada": parcel["layer"], "Área (ha)": f"{parcel['area_ha']:.4f}", **parcel["properties"]}
        extended = "".join(
            f'<Data name="{escape(key, {chr(34): "&quot;"})}"><value>{escape(value)}</value></Data>'
            for key, value in data.items()
        )
        placemarks.append(
            f"<Placemark><name>{escape(parcel['name'])}</name><styleUrl>#parcela</styleUrl>"
            f"<ExtendedData>{extended}</ExtendedData>{body}</Placemark>"
        )
    kml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        f"<name>{escape(title)}</name>"
        "<description>Parcelas selecionadas no Amazônika Geoespacial (WGS84).</description>"
        '<Style id="parcela"><LineStyle><color>ff0080ff</color><width>2</width></LineStyle>'
        "<PolyStyle><color>400080ff</color></PolyStyle></Style>"
        + "".join(placemarks)
        + "</Document></kml>"
    )
    return kml.encode("utf-8")


def _shapefile_zip(prepared: list[dict], title: str) -> bytes:
    keys: list[str] = []
    for parcel in prepared:
        for key in parcel["properties"]:
            if key not in keys:
                keys.append(key)
    mapping = _field_names(keys)
    rows = []
    for parcel in prepared:
        row = {
            "NOME": parcel["name"][:254],
            "CAMADA": parcel["layer"][:254],
            "AREA_HA": round(parcel["area_ha"], 4),
        }
        for key, field in mapping.items():
            row[field] = parcel["properties"].get(key, "")[:254]
        rows.append(row)
    frame = gpd.GeoDataFrame(
        rows,
        geometry=[parcel["geometry"] for parcel in prepared],
        crs="EPSG:4326",
    )
    # Shapefile exige um único tipo; polígonos simples viram MultiPolygon de uma parte.
    frame["geometry"] = frame.geometry.apply(
        lambda g: MultiPolygon([g]) if isinstance(g, Polygon) else g
    )
    with tempfile.TemporaryDirectory(prefix="amazonika-parcelas-") as directory:
        root = Path(directory)
        frame.to_file(
            root / "parcelas.shp", driver="ESRI Shapefile", engine="pyogrio",
            layer_options={"ENCODING": "UTF-8"},
        )
        with open(root / "atributos.csv", "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(["NOME", "CAMADA", "AREA_HA", *keys])
            for parcel in prepared:
                writer.writerow([
                    parcel["name"], parcel["layer"], f"{parcel['area_ha']:.4f}".replace(".", ","),
                    *[parcel["properties"].get(key, "") for key in keys],
                ])
        legend = "\n".join(f"{field} = {key}" for key, field in mapping.items())
        (root / "leia-me.txt").write_text(
            f"{title}\n"
            f"{len(prepared)} parcela(s) selecionada(s) no Amazônika Geoespacial.\n"
            "Sistema de referência: WGS84 (EPSG:4326), coordenadas geográficas.\n"
            "AREA_HA calculada no elipsoide GRS80.\n"
            "Os nomes de campo do Shapefile são limitados a 10 caracteres; "
            "os atributos completos estão em atributos.csv.\n"
            + (f"\nCampos:\n{legend}\n" if legend else ""),
            encoding="utf-8",
        )
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.iterdir()):
                if path.is_file():
                    archive.write(path, path.name)
        return output.getvalue()


def export_parcels(*, parcels: list[dict], filename: str, format: str) -> tuple[bytes, str, str]:
    prepared = _prepare(parcels)
    stem = _slug(filename)
    title = filename.strip() or "Parcelas selecionadas"
    if format == "kml":
        return _kml(prepared, title), f"{stem}.kml", "application/vnd.google-earth.kml+xml"
    if format == "shp":
        return _shapefile_zip(prepared, title), f"{stem}-shapefile.zip", "application/zip"
    raise ValueError("Formato inválido. Use kml ou shp.")
