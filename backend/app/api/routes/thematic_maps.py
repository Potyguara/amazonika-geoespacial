"""User-uploaded thematic vector datasets; generic thematic PDF output."""
import io
import json
import tempfile
from pathlib import Path
from zipfile import ZipFile, BadZipFile
import geopandas as gpd
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Response
from pydantic import BaseModel, Field
from shapely.geometry import mapping, shape
from app.services.auth import require_permission
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
        pdf = render_thematic_pdf(payload.title, payload.subtitle, layers, payload.source_text)
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="mapa-tematico.pdf"'})
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
