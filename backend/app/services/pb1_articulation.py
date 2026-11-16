"""Indexação de folhas do Amapá para identificar fontes cartográficas PB1.

A articulação WGS84 identifica folhas; NÃO certifica PEC ou o produto raster.
Instale o índice GeoJSON fora da imagem/container em PB1_ARTICULATION_GEOJSON.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from shapely.geometry import shape
from shapely.validation import explain_validity

def _load_features(index_path: str):
    path = Path(index_path)
    if not path.is_file():
        raise FileNotFoundError("Índice PB1 da articulação do Amapá não instalado.")
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("Índice de articulação excede o tamanho permitido.")
    collection = json.loads(path.read_text(encoding="utf-8"))
    if collection.get("type") != "FeatureCollection":
        raise ValueError("Índice PB1 deve ser FeatureCollection GeoJSON.")
    rows = []
    for feature in collection.get("features", []):
        props = feature.get("properties") or {}
        geom = shape(feature["geometry"])
        if geom.is_empty or not geom.is_valid:
            raise ValueError("Folha inválida no índice de articulação.")
        rows.append((geom, {
            "inom": str(props.get("INOM") or ""),
            "mi": str(props.get("MI_1") or ""),
            "bloco": str(props.get("Blocos") or ""),
        }))
    return rows

@lru_cache(maxsize=4)
def _cached_index(path: str, mtime_ns: int):
    return _load_features(path)

def identify_pb1_sheets(geometry: dict, index_path: str | None = None) -> dict:
    """Recebe Polygon/MultiPolygon em EPSG:4326 e retorna folhas intersectadas."""
    area = shape(geometry)
    if area.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("Informe um polígono ou multipolígono do imóvel.")
    if area.is_empty or not area.is_valid:
        raise ValueError(f"Geometria do imóvel inválida: {explain_validity(area)}")
    x0, y0, x1, y1 = area.bounds
    if not (-180 <= x0 <= x1 <= 180 and -90 <= y0 <= y1 <= 90):
        raise ValueError("Coordenadas fora de WGS84 longitude/latitude.")
    path = str(index_path or os.getenv("PB1_ARTICULATION_GEOJSON", ""))
    if not path or not Path(path).is_file():
        raise FileNotFoundError("Índice PB1 indisponível. Configure PB1_ARTICULATION_GEOJSON.")
    stat = Path(path).stat()
    entries = _cached_index(path, stat.st_mtime_ns)
    found = []
    for sheet, meta in entries:
        if not sheet.intersects(area):
            continue
        intersection = sheet.intersection(area)
        found.append({
            **meta,
            "area_overlap": intersection.area > 0,
            "boundary_touch_only": intersection.area == 0,
        })
    found.sort(key=lambda row: (row["bloco"], row["inom"]))
    return {
        "method_candidate": "PB1",
        "official_method": "Base cartográfica com precisão conhecida",
        "index_crs": "EPSG:4326",
        "matched_sheets": found,
        "sheet_count": len(found),
        "accuracy_status": "NOT_VERIFIED",
        "notice": "A articulação identifica folhas, não comprova precisão, PEC ou adequação do MDT Color para vetorizar o limite.",
    }
