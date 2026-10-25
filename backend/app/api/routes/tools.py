from __future__ import annotations

import json
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import geopandas as gpd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from pyproj import Geod
from shapely.geometry import shape

from app.core.config import get_settings
from app.services.auth import require_permission


router = APIRouter(
    prefix="/tools",
    tags=["Ferramentas geoespaciais"],
    dependencies=[Depends(require_permission("analysis.execute"))],
)


class MemorialRequest(BaseModel):
    geometry: dict[str, Any]
    title: str = Field(default="Área analisada", max_length=180)
    owner_name: str | None = Field(default=None, max_length=255)
    responsible_name: str | None = Field(default=None, max_length=255)
    vertex_prefix: str = Field(default="V", min_length=1, max_length=8)


def _format_dms(value: float, axis: str) -> str:
    absolute = abs(value)
    degrees = int(absolute)
    minutes_float = (absolute - degrees) * 60
    minutes = int(minutes_float)
    seconds = (minutes_float - minutes) * 60
    hemisphere = (
        ("S" if value < 0 else "N")
        if axis == "lat"
        else ("W" if value < 0 else "E")
    )
    return f"{degrees:02d}° {minutes:02d}' {seconds:06.3f}\" {hemisphere}"


def _polygon_vertices(geometry: dict[str, Any], prefix: str) -> tuple[list[dict], float, float]:
    geom = shape(geometry)
    if geom.geom_type not in {"Polygon", "MultiPolygon"}:
        raise HTTPException(422, "Planta e memorial exigem uma geometria poligonal.")
    if geom.is_empty or not geom.is_valid:
        raise HTTPException(422, "A geometria informada é vazia ou inválida.")

    polygon = max(geom.geoms, key=lambda item: item.area) if geom.geom_type == "MultiPolygon" else geom
    coords = list(polygon.exterior.coords)
    if len(coords) < 4:
        raise HTTPException(422, "A poligonal precisa possuir ao menos três vértices.")

    geod = Geod(ellps="GRS80")
    area_m2, perimeter_m = geod.geometry_area_perimeter(polygon)
    area_m2 = abs(area_m2)

    vertices: list[dict] = []
    unique = coords[:-1]
    for index, (lon, lat) in enumerate(unique):
        next_lon, next_lat = unique[(index + 1) % len(unique)]
        azimuth, _, distance = geod.inv(lon, lat, next_lon, next_lat)
        if azimuth < 0:
            azimuth += 360
        vertices.append(
            {
                "name": f"{prefix}{index + 1:02d}",
                "longitude": round(lon, 9),
                "latitude": round(lat, 9),
                "longitude_dms": _format_dms(lon, "lon"),
                "latitude_dms": _format_dms(lat, "lat"),
                "next_vertex": f"{prefix}{((index + 1) % len(unique)) + 1:02d}",
                "azimuth_degrees": round(azimuth, 6),
                "distance_meters": round(distance, 3),
            }
        )
    return vertices, area_m2 / 10000.0, perimeter_m


def _deterministic_memorial(payload: MemorialRequest, vertices: list[dict], area_ha: float, perimeter_m: float) -> str:
    lines = [
        f"MEMORIAL DESCRITIVO — {payload.title}",
        "",
        f"Detentor/Interessado: {payload.owner_name or 'Não informado'}",
        f"Responsável técnico: {payload.responsible_name or 'Não informado'}",
        f"Área: {area_ha:.4f} ha",
        f"Perímetro: {perimeter_m:.3f} m",
        "",
        "DESCRIÇÃO DO PERÍMETRO",
    ]
    for vertex in vertices:
        lines.append(
            f"Do vértice {vertex['name']}, de coordenadas {vertex['latitude_dms']} e "
            f"{vertex['longitude_dms']}, segue-se até o vértice {vertex['next_vertex']} "
            f"com azimute {vertex['azimuth_degrees']:.6f}° e distância "
            f"{vertex['distance_meters']:.3f} m."
        )
    lines.append("")
    lines.append("As grandezas geométricas foram calculadas pelo sistema; a redação deve ser conferida pelo responsável técnico antes da emissão.")
    return "\n".join(lines)


def _openai_memorial(payload: MemorialRequest, vertices: list[dict], area_ha: float, perimeter_m: float) -> str | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None

    numerical = {
        "title": payload.title,
        "owner_name": payload.owner_name,
        "responsible_name": payload.responsible_name,
        "area_hectares": round(area_ha, 4),
        "perimeter_meters": round(perimeter_m, 3),
        "vertices": vertices,
    }
    instructions = (
        "Redija um memorial descritivo técnico em português do Brasil. "
        "NÃO altere, arredonde novamente ou invente coordenadas, azimutes, distâncias, área ou perímetro. "
        "Use exatamente os valores fornecidos. Produza somente o corpo textual do memorial."
    )
    request_body = json.dumps(
        {
            "model": settings.openai_model,
            "input": [
                {
                    "role": "system",
                    "content": instructions,
                },
                {
                    "role": "user",
                    "content": json.dumps(numerical, ensure_ascii=False),
                },
            ],
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=request_body,
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise HTTPException(502, f"Falha ao gerar o texto com a OpenAI: {str(exc)[:220]}") from exc

    if isinstance(body.get("output_text"), str) and body["output_text"].strip():
        return body["output_text"].strip()

    parts: list[str] = []
    for item in body.get("output", []):
        for content in item.get("content", []) if isinstance(item, dict) else []:
            text_value = content.get("text") if isinstance(content, dict) else None
            if isinstance(text_value, str):
                parts.append(text_value)
    return "\n".join(parts).strip() or None


@router.post("/convert-vector")
def convert_vector(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".zip", ".kml", ".geojson", ".json", ".gpkg"}:
        raise HTTPException(422, "Formato não suportado. Use ZIP de Shapefile, KML, GeoJSON ou GeoPackage.")

    raw = file.file.read()
    if len(raw) > 150 * 1024 * 1024:
        raise HTTPException(413, "Arquivo excede o limite de 150 MB para importação direta no mapa.")

    with tempfile.TemporaryDirectory(prefix="amazonika-map-import-") as tmp:
        path = Path(tmp) / f"entrada{suffix}"
        path.write_bytes(raw)
        try:
            source = f"zip://{path}" if suffix == ".zip" else str(path)
            frame = gpd.read_file(source)
        except Exception as exc:
            raise HTTPException(422, f"Não foi possível ler o arquivo vetorial: {str(exc)[:240]}") from exc

        if frame.empty:
            raise HTTPException(422, "O arquivo não contém feições.")
        if len(frame) > 100000:
            raise HTTPException(422, "A importação direta no mapa aceita até 100.000 feições por arquivo.")
        if frame.crs is None:
            raise HTTPException(422, "O arquivo vetorial não possui sistema de referência (CRS).")

        frame = frame.to_crs("EPSG:4674")
        frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty]
        return json.loads(frame.to_json(drop_id=False))


@router.post("/memorial-draft")
def memorial_draft(payload: MemorialRequest):
    vertices, area_ha, perimeter_m = _polygon_vertices(payload.geometry, payload.vertex_prefix.upper())
    memorial = _openai_memorial(payload, vertices, area_ha, perimeter_m)
    ai_used = memorial is not None
    if memorial is None:
        memorial = _deterministic_memorial(payload, vertices, area_ha, perimeter_m)
    return {
        "title": payload.title,
        "area_hectares": round(area_ha, 4),
        "perimeter_meters": round(perimeter_m, 3),
        "vertices": vertices,
        "memorial_text": memorial,
        "ai_used": ai_used,
        "calculation_engine": "pyproj.Geod/GRS80",
    }
