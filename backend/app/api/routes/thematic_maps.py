"""User-uploaded thematic vector datasets; generic thematic PDF output."""
import io
import json
import tempfile
from uuid import uuid4
import os
import sqlite3
from datetime import datetime, timezone
from shapely.ops import unary_union
from shapely.geometry import box
from pathlib import Path
from zipfile import ZipFile, BadZipFile
import geopandas as gpd
import pyogrio
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Response
from pydantic import BaseModel, Field
from shapely.geometry import mapping, shape, Polygon, MultiPolygon, GeometryCollection
from app.services.auth import require_permission, get_current_user
from app.models.auth import User
from app.services.thematic_maps import Layer, TEMPLATES, PALETTE, render_thematic_pdf
from app.services.thematic_matplotlib import render_matplotlib

router = APIRouter(prefix="/thematic-maps", tags=["Mapas temáticos"],
                   dependencies=[Depends(require_permission("analysis.execute"))])

class MapLayer(BaseModel):
    name: str = Field(max_length=200)
    source: str = Field(max_length=250)
    color: str = Field(default="#73c6ad", max_length=7)
    role: str = Field(default="theme")
    geometry: dict

class CartographicStyle(BaseModel):
    mode: str = "minimalista"
    grid: str = "border"
    property: str = "outline"
    context: str = "balanced"
    scale: float | None = None
    buffer_m: float | None = None


class MapRequest(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    subtitle: str = Field(default="", max_length=150)
    source_text: str = Field(default="", max_length=600)
    layers: list[MapLayer] = Field(min_length=1, max_length=60)
    style: CartographicStyle = Field(default_factory=CartographicStyle)
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
        pdf = render_matplotlib(payload.title, payload.subtitle, layers, payload.source_text, branding=payload.include_branding, style=payload.style.model_dump())
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



def _catalog_path(user: User) -> Path:
    return PACKAGE_ROOT / str(user.id) / "catalog.json"


def _catalog(user: User) -> list:
    path = _catalog_path(user)
    if not path.exists():
        # Importações anteriores à biblioteca também ficam disponíveis.
        root = path.parent
        records = []
        for item in sorted(root.glob("*.gpkg")):
            try:
                names = [row[0] for row in pyogrio.list_layers(str(item)) if row[1]]
                records.append({"package_id": item.stem, "name": item.name,
                                "layers": [{"name": n} for n in names],
                                "size_bytes": item.stat().st_size,
                                "created_at": datetime.fromtimestamp(item.stat().st_mtime, timezone.utc).isoformat()})
            except (ValueError, OSError):
                continue
        if records:
            _save_catalog(user, records)
        return records
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
        return [p for p in items if _user_package(user, p["package_id"]).is_file()]
    except (ValueError, KeyError, TypeError):
        return []


def _save_catalog(user: User, items: list):
    path = _catalog_path(user)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


@router.get("/packages")
def list_packages(user: User = Depends(get_current_user)):
    return _catalog(user)


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
                if size > 50_000_000:
                    raise HTTPException(413, "GeoPackage excede 50 MB.")
                output.write(chunk)
        with path.open("rb") as header_file:
            header = header_file.read(16)
        if header != b"SQLite format 3" + bytes([0]):
            raise ValueError("Arquivo não é um GeoPackage SQLite válido.")
        names = [row[0] for row in pyogrio.list_layers(str(path)) if row[1]]
        if not names or len(names) > 80:
            raise ValueError("Pacote sem camadas ou com mais de 80 camadas.")
        layers = []
        for name in names:
            info = pyogrio.read_info(str(path), layer=name)
            if not info.get("crs"):
                raise ValueError(f"Camada {name} sem SRC definido.")
            layers.append({"name": name, "features": info.get("features"),
                           "geometry_type": info.get("geometry_type"),
                           "source_crs": str(info["crs"])})
        record = {"package_id": package_id, "name": Path(file.filename or "").name,
                  "layers": layers, "size_bytes": size,
                  "created_at": datetime.now(timezone.utc).isoformat()}
        _save_catalog(user, [record, *_catalog(user)])
        return record
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
    class_fields: dict[str, str] = Field(default_factory=dict)
    style: CartographicStyle = Field(default_factory=CartographicStyle)
    class_colors: dict[str, str] = Field(default_factory=dict)
    layer_colors: dict[str, str] = Field(default_factory=dict)
    include_branding: bool = False
    source_text: str = Field(default="", max_length=600)
    property_name: str = Field(default="", max_length=120)
    municipality: str = Field(default="", max_length=80)
    state: str = Field(default="", max_length=2)
    responsible: str = Field(default="", max_length=120)


def normalize_property_polygon(value: dict):
    """Extract all polygonal features from GeoJSON GeometryCollections/FeatureCollections."""
    def gather(obj):
        if not isinstance(obj, dict):
            return []
        kind = obj.get("type")
        if kind == "FeatureCollection":
            return [p for f in obj.get("features", []) for p in gather(f)]
        if kind == "Feature":
            return gather(obj.get("geometry"))
        if kind == "GeometryCollection":
            return [p for g in obj.get("geometries", []) for p in gather(g)]
        try:
            geom = shape(obj)
        except (TypeError, ValueError, KeyError):
            return []
        if isinstance(geom, Polygon):
            return [geom]
        if isinstance(geom, MultiPolygon):
            return list(geom.geoms)
        return []
    polygons = [p for p in gather(value) if not p.is_empty and p.is_valid and p.area > 0]
    if not polygons:
        raise HTTPException(422, "A propriedade não contém polígonos válidos. Importe um perímetro fechado.")
    result = unary_union(polygons)
    if result.is_empty or not result.is_valid:
        raise HTTPException(422, "Os polígonos da propriedade possuem geometria inválida.")
    return result


@router.post("/package/pdf")
def render_package_pdf(payload: PackageMapRequest, user: User = Depends(get_current_user)):
    path = _user_package(user, payload.package_id)
    if not path.is_file():
        raise HTTPException(404, "GeoPackage não localizado.")
    prop = normalize_property_polygon(payload.property_geometry)
    # CRS canonical for file upload property: EPSG:4674.
    from app.services.thematic_maps import _color
    from shapely.ops import transform
    from pyproj import Transformer
    import math
    bounds = prop.bounds
    radius = max(bounds[2]-bounds[0], bounds[3]-bounds[1], .01)
    roi = box(bounds[0]-radius*.4,bounds[1]-radius*.4,
              bounds[2]+radius*.4,bounds[3]+radius*.4)
    if os.environ.get("THEMATIC_RENDERER", "matplotlib") == "pyqgis":
        from app.services.thematic_pyqgis_package import render_package_pyqgis
        try:
            result = render_package_pyqgis(path, payload, prop, roi)
        except ValueError as exc:
            raise HTTPException(422, str(exc)[:220]) from exc
        except Exception as exc:
            raise HTTPException(502, "Serviço PyQGIS indisponível ou falhou na renderização.") from exc
        return Response(content=result, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="mapa-tematico.pdf"'})
    layers = []
    available = set([row[0] for row in pyogrio.list_layers(str(path)) if row[1]])
    if any(name not in available for name in payload.selected_layers):
        raise HTTPException(422, "Camada não existe no pacote.")
    for index, name in enumerate(payload.selected_layers):
        try:
            frame = gpd.read_file(path, layer=name, bbox=gpd.GeoSeries([roi], crs="EPSG:4674"))
            if frame.empty:
                continue
            if frame.crs is None:
                raise ValueError("SRC não informado.")
            frame = frame.to_crs("EPSG:4674")
            frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty]
            # Preserve geological/pedological classes instead of dissolving all units.
            candidates = [c for c in frame.columns if c != frame.geometry.name]
            preferred = payload.class_fields.get(name)
            if preferred and preferred not in candidates:
                raise ValueError("Campo de classificação indisponível.")
            if not preferred:
                terms = ("classe", "unidade", "sigla", "tipo", "nome", "descricao", "litologia", "solo")
                preferred = next((c for c in candidates if any(t in c.casefold() for t in terms)
                                  and 1 < frame[c].nunique(dropna=True) <= 12), None)
            groups = frame.groupby(frame[preferred].fillna("Não classificado").astype(str)) if preferred else [(name, frame)]
            groups = list(groups)
            from app.services.thematic_maps import category_shade
            for class_index, (category, subset) in enumerate(groups):
                clipped = subset.geometry.intersection(roi)
                geoms = [g for g in clipped if not g.is_empty and g.is_valid]
                if geoms:
                    geom = unary_union(geoms)
                    label = f"{name}: {str(category)[:60]}" if preferred else name
                    layers.append(Layer(label, f"GeoPackage: {name}", geom,
                                        payload.class_colors.get(label, category_shade(payload.layer_colors.get(name, PALETTE[index % len(PALETTE)]), class_index, len(groups))), "theme"))
        except Exception as exc:
            raise HTTPException(422, f"Camada {name}: {str(exc)[:160]}") from exc
    if not layers:
        raise HTTPException(422, "Nenhuma camada temática intersecta o entorno da propriedade.")
    layers.append(Layer("Propriedade", "Geometria fornecida pelo usuário",
                        prop, "#d02020", "property"))
    result = render_matplotlib(payload.title,payload.subtitle,layers,
                                payload.source_text, branding=payload.include_branding,
                                style=payload.style.model_dump())
    return Response(content=result,media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="mapa-tematico.pdf"'})


@router.post("/package/suggestions")
def suggest_package_layers(payload: PackageMapRequest, user: User = Depends(get_current_user)):
    path = _user_package(user, payload.package_id)
    if not path.is_file():
        raise HTTPException(404, "GeoPackage não localizado.")
    # Local, explainable baseline. Never generate geometry or factual features through AI.
    import re
    names = [row[0] for row in pyogrio.list_layers(str(path))]
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
    # IA opcional: recomenda apenas nomes existentes, nunca altera geometrias.
    from app.core.config import get_settings
    cfg = get_settings()
    ai_used = False
    if cfg.openai_api_key:
        try:
            import urllib.request
            request = urllib.request.Request(
                "https://api.openai.com/v1/responses",
                data=json.dumps({
                    "model": cfg.openai_model,
                    "input": [
                        {"role": "system", "content":
                         "Você é assistente cartográfico. Escolha APENAS nomes de camadas existentes "
                         "apropriados ao tema. Responda somente JSON: "
                         "{\\\"layers\\\":[\\\"nome exato\\\"]}. Não invente dados ou geometrias."},
                        {"role": "user", "content": json.dumps({
                            "tema": payload.title, "camadas_disponiveis": names[:80],
                            "regras_sugerem": matches
                        }, ensure_ascii=False)}
                    ],
                    "max_output_tokens": 300
                }).encode("utf-8"),
                headers={"Authorization": "Bearer " + cfg.openai_api_key,
                         "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=12) as response:
                result = json.load(response)
            content = "".join(part.get("text", "") for block in result.get("output", [])
                              for part in block.get("content", [])
                              if part.get("type") == "output_text")
            proposed = json.loads(content).get("layers", [])
            valid = [name for name in proposed if isinstance(name, str) and name in names]
            if valid:
                matches = list(dict.fromkeys(valid))
                ai_used = True
        except (ValueError, KeyError, TimeoutError, OSError, TypeError):
            pass
    return {"suggested_layers": matches, "all_layers": names,
            "method": "ia_assistida" if ai_used else "regras_cartograficas",
            "ai_used": ai_used,
            "note": "IA só sugere camadas existentes; confira as fontes e geometria antes de gerar."}


class DesignRequest(BaseModel):
    package_id: str
    template: str = Field(max_length=80)
    selected_layers: list[str] = Field(min_length=1, max_length=30)


@router.post("/package/design")
def design_map(payload: DesignRequest, user: User = Depends(get_current_user)):
    """AI-assisted cartographic design; only schema/sample attributes, never geometries."""
    import urllib.request
    from app.core.config import get_settings
    path = _user_package(user, payload.package_id)
    if not path.exists():
        raise HTTPException(404, "Base não encontrada.")
    allowed = set(row[0] for row in pyogrio.list_layers(str(path)) if row[1])
    if any(name not in allowed for name in payload.selected_layers):
        raise HTTPException(422, "Seleção contém camada inexistente.")
    metadata = []
    for name in payload.selected_layers:
        info = pyogrio.read_info(str(path), layer=name)
        candidates = []
        for field in info.get("fields", []):
            field = str(field)
            if field == "geometry":
                continue
            # Bounded, representative attribute samples, never unrestricted dataset extraction.
            try:
                preview = gpd.read_file(path, layer=name, columns=[field], max_features=120)
                values = [str(x)[:65] for x in preview[field].dropna().unique()[:12]]
                if values:
                    candidates.append({"field": field, "examples": values})
            except (ValueError, KeyError, TypeError):
                continue
            if len(candidates) >= 12:
                break
        metadata.append({"name": name, "geometry": info.get("geometry_type"),
                         "fields": candidates})
    # Deterministic, transparent fallback for unavailable AI / quota limits.
    defaults = []
    for index, item in enumerate(metadata):
        options = item["fields"]
        key = ("classe", "unidade", "litolog", "tipo", "nome", "sigla", "solo", "veget")
        pick = next((f["field"] for f in options if any(word in f["field"].casefold() for word in key)), None)
        defaults.append({"layer": item["name"], "class_field": pick,
                         "color": PALETTE[index % len(PALETTE)], "reason": "Regras cartográficas"})
    result = {"design": defaults, "ai_used": False, "metadata": metadata,
              "usage": None, "note": "Confira todas as sugestões antes de aplicar."}
    settings = get_settings()
    if not settings.openai_api_key:
        return result
    try:
        from app.services.thematic_maps import _color
        prompt = {
            "template": payload.template, "layers": metadata,
            "rules": "Retorne JSON com chave design, lista de objetos com layer, class_field, color, reason. "
                     "Use exatamente os nomes e campos fornecidos; class_field pode ser null. "
                     "Color deve ser #RRGGBB; escolha cores contrastantes, hidrografia azul, "
                     "propriedade não está neste pacote. Não infira descrições de códigos."
        }
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps({"model": settings.openai_model,
                "input": [{"role": "system", "content":
                           "Você é assistente de cartografia temática. Nunca invente camadas, campos, "
                           "coordenadas nem atributos. Responda SOMENTE JSON."},
                          {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}],
                "max_output_tokens": 1200}).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + settings.openai_api_key},
            method="POST")
        with urllib.request.urlopen(request, timeout=25) as response:
            answer = json.load(response)
        raw = "".join(part.get("text", "") for block in answer.get("output", [])
                      for part in block.get("content", []) if part.get("type") == "output_text")
        proposed = json.loads(raw).get("design", [])
        by_name = {p["layer"]: p for p in proposed if isinstance(p, dict) and isinstance(p.get("layer"), str)}
        verified = []
        for default, item in zip(defaults, metadata):
            proposal = by_name.get(item["name"], {})
            fields = {f["field"] for f in item["fields"]}
            field = proposal.get("class_field")
            if field not in fields:
                field = default["class_field"]
            color = proposal.get("color", "")
            try:
                _color(color)
            except (ValueError, TypeError):
                color = default["color"]
            verified.append({"layer": item["name"], "class_field": field,
                             "color": color, "reason": str(proposal.get("reason", ""))[:180]})
        result.update(design=verified, ai_used=True, usage=answer.get("usage"))
    except (ValueError, KeyError, TypeError, OSError, TimeoutError):
        result["note"] = "IA indisponível; recomendações locais aplicadas."
    return result
