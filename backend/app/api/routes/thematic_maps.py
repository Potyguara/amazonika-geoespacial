"""User-uploaded thematic vector datasets; generic thematic PDF output."""
import io
import json
import tempfile
from uuid import uuid4
import os
import sqlite3
from shapely.ops import unary_union
from shapely.geometry import box
from pathlib import Path
from zipfile import ZipFile, BadZipFile
import geopandas as gpd
import fiona
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Response
from pydantic import BaseModel, Field
from shapely.geometry import mapping, shape
from app.services.auth import require_permission, get_current_user
from app.models.auth import User
from app.services.thematic_maps import Layer, TEMPLATES, PALETTE, render_thematic_pdf

router = APIRouter(prefix="/thematic-maps", tags=["Mapas temáticos"],
                   dependencies=[Depends(require_permission("analysis.execute"))])

class MapLayer(BaseModel):
    name: str = Field(max_length=200)
    source: str = Field(max_length=250)
    color: str = Field(default="#73c6ad", max_length=7)
    role: str = Field(default="theme")
    geometry: dict

class MapRequest(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    subtitle: str = Field(default="", max_length=150)
    source_text: str = Field(default="", max_length=600)
    layers: list[MapLayer] = Field(min_length=1, max_length=60)
    include_branding: bool = False


@router.get("/templates")
def templates():
    return [{"code": code, "title": title} for code, title in TEMPLATES]


@router.post("/import")
async def import_vector(file: UploadFile = File(...)):
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if suffix not in (".zip", ".gpkg", ".kml", ".geojson"):
        raise HTTPException(422, "Envie ZIP Shapefile, GPKG, KML ou GeoJSON.")
    raw = await file.read(25_000_001)
    if len(raw) > 25_000_000:
        raise HTTPException(413, "Arquivo excede 25 MB.")
    try:
        with tempfile.TemporaryDirectory() as dirname:
            path = Path(dirname) / ("uploaded" + suffix)
            path.write_bytes(raw)
            if suffix == ".zip":
                with ZipFile(path) as archive:
                    names = archive.namelist()
                    if len(names) > 100 or sum(i.file_size for i in archive.infolist()) > 120_000_000:
                        raise ValueError("ZIP excede o limite de arquivos ou tamanho.")
                    if any(i.filename.startswith("/") or ".." in Path(i.filename).parts for i in archive.infolist()):
                        raise ValueError("ZIP contém caminho inválido.")
                    archive.extractall(Path(dirname) / "shape")
                shp = list((Path(dirname) / "shape").rglob("*.shp"))
                if len(shp) != 1:
                    raise ValueError("O ZIP deve conter exatamente um arquivo SHP.")
                frame = gpd.read_file(shp[0])
            else:
                frame = gpd.read_file(path)
            if frame.crs is None:
                raise ValueError("O arquivo não informa SRC. Defina o SRC antes de importar.")
            if len(frame) > 3000:
                raise ValueError("Camada excede 3.000 feições.")
            frame = frame.to_crs("EPSG:4674")
            frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty]
            if frame.empty:
                raise ValueError("Arquivo sem geometrias válidas.")
            # GeoJSON size bound; no non-geometric attributes are needed for first release.
            geometries = [mapping(g) for g in frame.geometry]
            if len(json.dumps(geometries)) > 9_000_000:
                raise ValueError("Geometrias complexas demais para exportação direta.")
            from shapely.geometry import GeometryCollection
            combined = GeometryCollection(list(frame.geometry))
            return {"filename": filename, "features": len(frame),
                    "geometry": mapping(combined), "source_crs": str(frame.crs)}
    except (ValueError, BadZipFile) as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(422, "Não foi possível interpretar o arquivo vetorial.") from exc


@router.post("/pdf")
def generate_pdf(payload: MapRequest):
    try:
        layers = []
        for layer in payload.layers:
            if layer.role not in ("property", "theme"):
                raise ValueError("Papel de camada inválido.")
            geom = shape(layer.geometry)
            if geom.is_empty or not geom.is_valid:
                raise ValueError(f"Geometria inválida: {layer.name}.")
            layers.append(Layer(layer.name, layer.source, geom, layer.color, layer.role))
        pdf = render_thematic_pdf(payload.title, payload.subtitle, layers, payload.source_text, include_branding=payload.include_branding)
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="mapa-tematico.pdf"'})
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

# Pacotes são mantidos no volume persistente da API. A propriedade é sempre importada à parte.
PACKAGE_ROOT = Path(os.environ.get("STORAGE_DIR", "/tmp")) / "thematic-packages"


def _user_package(user: User, package_id: str) -> Path:
    from uuid import UUID
    try:
        package_id = str(UUID(package_id))
    except (ValueError, AttributeError):
        raise HTTPException(422, "Identificador inválido.")
    return PACKAGE_ROOT / str(user.id) / (package_id + ".gpkg")


@router.post("/package")
async def upload_package(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    if Path(file.filename or "").suffix.lower() != ".gpkg":
        raise HTTPException(422, "O pacote temático deve ser GeoPackage (.gpkg).")
    package_id = str(uuid4())
    path = _user_package(user, package_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > 300_000_000:
                    raise HTTPException(413, "GeoPackage excede 300 MB.")
                output.write(chunk)
        if path.read_bytes()[:16] != b"SQLite format 3\\x00":
            raise ValueError("Arquivo não é um GeoPackage SQLite válido.")
        names = fiona.listlayers(str(path))
        if not names or len(names) > 80:
            raise ValueError("Pacote sem camadas ou com mais de 80 camadas.")
        layers = []
        for name in names:
            with fiona.open(path, layer=name) as source:
                if not source.crs:
                    raise ValueError(f"Camada {name} sem SRC definido.")
                layers.append({"name": name, "features": len(source),
                               "geometry_type": source.schema.get("geometry"),
                               "source_crs": str(source.crs)})
        return {"package_id": package_id, "layers": layers, "size_bytes": size}
    except HTTPException:
        path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(422, f"Pacote inválido: {str(exc)[:220]}") from exc


class PackageMapRequest(BaseModel):
    package_id: str
    property_geometry: dict
    title: str = Field(min_length=1, max_length=150)
    subtitle: str = Field(default="", max_length=150)
    selected_layers: list[str] = Field(min_length=1, max_length=60)
    include_branding: bool = False
    source_text: str = Field(default="", max_length=600)


@router.post("/package/pdf")
def render_package_pdf(payload: PackageMapRequest, user: User = Depends(get_current_user)):
    path = _user_package(user, payload.package_id)
    if not path.is_file():
        raise HTTPException(404, "GeoPackage não localizado.")
    prop = shape(payload.property_geometry)
    if prop.is_empty or not prop.is_valid or prop.geom_type not in ("Polygon", "MultiPolygon"):
        raise HTTPException(422, "Forneça uma propriedade poligonal válida.")
    # CRS canonical for file upload property: EPSG:4674.
    from app.services.thematic_maps import _color
    from shapely.ops import transform
    from pyproj import Transformer
    import math
    bounds = prop.bounds
    radius = max(bounds[2]-bounds[0], bounds[3]-bounds[1], .01)
    roi = box(bounds[0]-radius*.4,bounds[1]-radius*.4,
              bounds[2]+radius*.4,bounds[3]+radius*.4)
    layers = []
    available = set(fiona.listlayers(str(path)))
    if any(name not in available for name in payload.selected_layers):
        raise HTTPException(422, "Camada não existe no pacote.")
    for index, name in enumerate(payload.selected_layers):
        try:
            frame = gpd.read_file(path, layer=name, bbox=tuple(roi.bounds))
            if frame.empty:
                continue
            if frame.crs is None:
                raise ValueError("SRC não informado.")
            frame = frame.to_crs("EPSG:4674")
            frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty]
            # Use a fixed geographic window for layout, do not alter original geometries.
            clipped = frame.geometry.intersection(roi)
            geoms = [g for g in clipped if not g.is_empty and g.is_valid]
            if geoms:
                geom = unary_union(geoms)
                layers.append(Layer(name, f"GeoPackage: {name}", geom,
                                    PALETTE[index % len(PALETTE)], "theme"))
        except Exception as exc:
            raise HTTPException(422, f"Camada {name}: {str(exc)[:160]}") from exc
    if not layers:
        raise HTTPException(422, "Nenhuma camada temática intersecta o entorno da propriedade.")
    layers.append(Layer("Propriedade", "Geometria fornecida pelo usuário",
                        prop, "#d02020", "property"))
    result = render_thematic_pdf(payload.title,payload.subtitle,layers,
                                 payload.source_text, include_branding=payload.include_branding)
    return Response(content=result,media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="mapa-tematico.pdf"'})


@router.post("/package/suggestions")
def suggest_package_layers(payload: PackageMapRequest, user: User = Depends(get_current_user)):
    path = _user_package(user, payload.package_id)
    if not path.is_file():
        raise HTTPException(404, "GeoPackage não localizado.")
    # Local, explainable baseline. Never generate geometry or factual features through AI.
    import re
    names = fiona.listlayers(str(path))
    groups = {
        "hidrografia": ("hidro", "rio", "dren", "igarap", "nascent"),
        "pedologia": ("solo", "pedolog"),
        "vegetacao": ("veget", "florest", "fitofision"),
        "geologia": ("geolog", "litolog"),
        "geomorfologia": ("geomorf", "relevo"),
        "ucs": ("conserv", "uc_", "icmbio", "parque"),
        "flota": ("flota", "amortec"),
        "acessos": ("acesso", "rodov", "via", "estrada"),
        "uso-solo": ("uso", "ocup", "cobertura"),
        "situacao": ("municip", "localid", "rodov", "hidro", "acesso"),
    }
    words = groups.get(payload.title.lower().strip(), ())
    matches = [n for n in names if any(w in n.casefold() for w in words)]
    return {"suggested_layers": matches, "all_layers": names,
            "method": "regras_cartograficas", "ai_used": False,
            "note": "Sugestões locais; confira as camadas e seus metadados antes de gerar."}
