"""Build a thematic PyQGIS request from a persisted, user-scoped GeoPackage.

The API validates package ownership before calling this helper. No database path or
user-supplied executable code is passed to the isolated cartography worker.
"""
from __future__ import annotations

import json
import math
import os
import urllib.request

import geopandas as gpd
import pyogrio
from shapely.geometry import mapping
from app.services.thematic_maps import PALETTE, category_shade

MAX_FEATURES_PER_LAYER = 3000
MAX_REQUEST_BYTES = 11_500_000
MAX_CATEGORIES = 40


def render_package_pyqgis(path, payload, prop, roi):
    available = {row[0] for row in pyogrio.list_layers(str(path)) if row[1]}
    if any(name not in available for name in payload.selected_layers):
        raise ValueError("Camada não existe no pacote.")
    output_layers = []
    for index, name in enumerate(payload.selected_layers):
        frame = gpd.read_file(path, layer=name, bbox=gpd.GeoSeries([roi], crs="EPSG:4674"))
        if frame.empty:
            continue
        if frame.crs is None:
            raise ValueError(f"Camada {name} sem SRC.")
        frame = frame.to_crs("EPSG:4674")
        frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty].copy()
        if frame.empty:
            continue
        frame.geometry = frame.geometry.intersection(roi)
        frame = frame[~frame.geometry.is_empty & frame.geometry.is_valid]
        if frame.empty:
            continue
        if len(frame) > MAX_FEATURES_PER_LAYER:
            raise ValueError(f"Camada {name} contém mais de {MAX_FEATURES_PER_LAYER} feições na área.")
        candidates = [c for c in frame.columns if c != frame.geometry.name]
        preferred = payload.class_fields.get(name)
        if preferred and preferred not in candidates:
            raise ValueError(f"Campo de classificação indisponível na camada {name}.")
        if not preferred:
            terms = ("classe", "unidade", "sigla", "tipo", "nome", "descricao", "litologia", "solo")
            preferred = next((c for c in candidates if any(t in c.casefold() for t in terms)
                              and 1 < frame[c].nunique(dropna=True) <= MAX_CATEGORIES), None)
        base_color = payload.layer_colors.get(name, PALETTE[index % len(PALETTE)])
        layer = {"name":name, "role":"theme", "color":base_color}
        if preferred:
            # Use string categories consistently, including nulls, for exact renderer matches.
            categories = frame[preferred].fillna("Não classificado").astype(str)
            values = sorted(categories.unique().tolist())
            if len(values) > MAX_CATEGORIES:
                raise ValueError(f"Camada {name} possui mais de {MAX_CATEGORIES} classes.")
            labels = [f"{name}: {value}" for value in values]
            layer["class_field"] = "amazonika_class"
            layer["classes"] = [
                {"value":value, "label":value[:70],
                 "color":payload.class_colors.get(labels[j],
                     category_shade(base_color, j, len(values)))}
                for j,value in enumerate(values)
            ]
            layer["features"] = [
                {"type":"Feature", "properties":{"amazonika_class":category},
                 "geometry":mapping(geom)}
                for geom, category in zip(frame.geometry, categories)
            ]
        else:
            layer["features"] = [
                {"type":"Feature","properties":{},"geometry":mapping(geom)}
                for geom in frame.geometry
            ]
        output_layers.append(layer)
    if not output_layers:
        raise ValueError("Nenhuma camada temática intersecta o entorno da propriedade.")
    output_layers.append({
        "name":"Propriedade", "role":"property", "color":"#d02020",
        "geometry":mapping(prop)
    })
    request = {
        "title":payload.title, "subtitle":payload.subtitle,
        "source":payload.source_text, "branding":payload.include_branding,
        "style":payload.style.model_dump(), "layers":output_layers,
        "metadata": {"property_name": payload.property_name,
                     "municipality":payload.municipality, "state":payload.state,
                     "responsible":payload.responsible}
    }
    data = json.dumps(request, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(data) > MAX_REQUEST_BYTES:
        raise ValueError("Geometrias excedem o limite do renderizador PyQGIS.")
    endpoint = os.environ.get("CARTOGRAPHY_URL","http://cartography-worker:8090").rstrip("/")
    req = urllib.request.Request(endpoint+"/render", data=data,
                                 headers={"Content-Type":"application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=90) as response:
        result = response.read(30_000_001)
    if len(result) > 30_000_000 or not result.startswith(b"%PDF"):
        raise ValueError("PyQGIS não retornou um PDF válido.")
    return result
