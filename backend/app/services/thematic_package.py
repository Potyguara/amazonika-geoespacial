"""Controlled GeoPackage upload, layer discovery and spatial extraction."""
import json
import re
import uuid
from pathlib import Path

import geopandas as gpd
import fiona
from shapely.geometry import mapping
from shapely.ops import unary_union

from app.core.config import get_settings

MAX_BYTES = 350 * 1024 * 1024
MAX_FEATURES_OUTPUT = 6000
ROLE_HINTS = {
    "property": ("propriedade", "imovel", "gleba", "fazenda", "perimetro", "poligonal"),
    "hidrografia": ("hidro", "drenagem", "rios", "igarape", "nascentes"),
    "acessos": ("vias", "acesso", "estrada", "rodovia", "malha_viaria"),
    "ucs": ("uc_", "unidade_conservacao", "icmbio", "parque", "reserva"),
    "flota": ("flota", "amortecimento", "za_"),
    "geologia": ("geologia", "geologico", "lito"),
    "geomorfologia": ("geomorf", "relevo"),
    "pedologia": ("solo", "pedolog"),
    "vegetacao": ("vegetacao", "fitofisionomia"),
    "uso-solo": ("uso_solo", "ocupacao", "cobertura"),
}


def storage_dir():
    directory = Path(get_settings().storage_dir) / "thematic_packages"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def package_file(package_id):
    try:
        clean = str(uuid.UUID(package_id))
    except (ValueError, AttributeError) as exc:
        raise ValueError("Identificador de pacote inválido.") from exc
    path = storage_dir() / (clean + ".gpkg")
    if not path.exists():
        raise ValueError("Pacote cartográfico inexistente.")
    return path


def classify(name):
    normalized = re.sub(r"[^a-z0-9_]+", "_", name.lower())
    for role, hints in ROLE_HINTS.items():
        if any(h in normalized for h in hints):
            return role
    return "theme"


def discover(path):
    layers = []
    for name in fiona.listlayers(str(path)):
        with fiona.open(path, layer=name) as collection:
            count = len(collection)
            role = classify(name)
            layers.append({
                "name": name, "features": count, "role_hint": role,
                "geometry_type": collection.schema.get("geometry", "Unknown"),
                "source_crs": str(collection.crs),
                "source": "GeoPackage: " + name,
                "columns": list(collection.schema.get("properties", {}))[:30],
            })
    return layers


def extract(path, layer_name, property_name, buffer_m=2500):
    available = fiona.listlayers(str(path))
    if layer_name not in available or property_name not in available:
        raise ValueError("Camada não encontrada no GeoPackage.")
    if not 0 <= buffer_m <= 100000:
        raise ValueError("Distância de recorte inválida.")
    property_frame = gpd.read_file(path, layer=property_name)
    if property_frame.crs is None or property_frame.empty:
        raise ValueError("Propriedade vazia ou sem SRC.")
    property_frame = property_frame.to_crs("EPSG:4674")
    prop = unary_union(list(property_frame.geometry.dropna()))
    if prop.is_empty:
        raise ValueError("Propriedade sem geometria.")
    if layer_name == property_name:
        clipped = property_frame
    else:
        # Work in local metric projection for reliable buffer; avoid loading full
        # state-wide layers before spatial filtering.
        metric = property_frame.estimate_utm_crs()
        if metric is None:
            raise ValueError("Não foi possível calcular o fuso UTM.")
        envelope = gpd.GeoSeries([prop], crs="EPSG:4674").to_crs(metric).buffer(buffer_m).to_crs("EPSG:4674").iloc[0]
        frame = gpd.read_file(path, layer=layer_name, bbox=tuple(envelope.bounds))
        if frame.crs is None:
            raise ValueError("Camada temática sem SRC.")
        frame = frame.to_crs("EPSG:4674")
        clipped = frame[frame.geometry.intersects(envelope)].copy()
        if len(clipped) > MAX_FEATURES_OUTPUT:
            raise ValueError("Muitas feições na região. Reduza a distância de recorte.")
        clipped["geometry"] = clipped.geometry.intersection(envelope)
    clipped = clipped[clipped.geometry.notna() & ~clipped.geometry.is_empty]
    if clipped.empty:
        raise ValueError("Nenhuma feição encontrada no entorno da propriedade.")
    geometries = [mapping(g) for g in clipped.geometry]
    packed = json.dumps(geometries)
    if len(packed) > 9_000_000:
        raise ValueError("Geometria extensa. Reduza a área de recorte.")
    from shapely.geometry import GeometryCollection
    return {
        "geometry": mapping(GeometryCollection(list(clipped.geometry))),
        "features": len(clipped), "name": layer_name,
        "source": "GeoPackage: " + layer_name,
        "attributes": list(clipped.columns.drop("geometry"))[:25],
    }
