from __future__ import annotations

import json
import os
import tempfile
from uuid import UUID, uuid4
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import geopandas as gpd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Response
from pydantic import BaseModel, Field
from pyproj import Geod
from shapely.geometry import shape

from app.core.config import get_settings
from app.services.geospatial_export import export_polygon
from app.services.plant_memorial_v2 import prepare_parcels, build_joint_memorial
from app.services.plant_memorial_v3 import make_joint_pdf
from app.services.preliminary_pdf_stamp import stamp_preliminary_pdf
from app.services.memorial_docx import build_memorial_docx
from app.services.auth import require_permission, get_current_user
from app.models.auth import User
from app.services.plant_memorial import (
    build_plant_memorial_pdf,
    load_document_template,
    save_document_logo,
    save_document_template,
)


router = APIRouter(
    prefix="/tools",
    tags=["Ferramentas geoespaciais"],
    dependencies=[Depends(require_permission("analysis.execute"))],
)


class MemorialParcel(BaseModel):
    name: str = Field(max_length=120)
    geometry: dict[str, Any]
    vertex_names: list[str] | None = None
    confrontants: list[str] | None = None
    altitudes_m: list[float | None] | None = None
    normal_altitudes_m: list[float | None] | None = None
    mdt_altitudes_m: list[float | None] | None = None
    is_preliminary: bool = False


class ProfessionalDocumentOverride(BaseModel):
    """Dados editáveis para uma única peça; não atualiza o perfil da conta."""
    full_name: str | None = Field(default=None, max_length=255)
    rg: str | None = Field(default=None, max_length=50)
    cpf: str | None = Field(default=None, max_length=18)
    profession: str | None = Field(default=None, max_length=150)
    specialization: str | None = Field(default=None, max_length=255)
    crea: str | None = Field(default=None, max_length=100)
    visto: str | None = Field(default=None, max_length=100)
    incra_code: str | None = Field(default=None, max_length=80)
    art: str | None = Field(default=None, max_length=120)


class PlantElements(BaseModel):
    title: bool = True
    grid: bool = True
    north: bool = True
    scale_text: bool = True
    scale_bar: bool = False
    vertex_labels: bool = True
    azimuths: bool = True
    distances: bool = True
    confrontants: bool = True
    coordinates: bool = True
    situation: bool = True
    technical_stamp: bool = True
    magnetic_declination: bool = True


def _document_professional(user: User, payload: "MemorialRequest") -> dict:
    professional = {"full_name": user.full_name, **(user.professional_profile_json or {})}
    if payload.professional_override is not None:
        professional.update({
            key: value.strip() if isinstance(value, str) else value
            for key, value in payload.professional_override.model_dump(exclude_none=True).items()
        })
    return professional


class MemorialRequest(BaseModel):
    geometry: dict[str, Any] | None = None
    parcels: list[MemorialParcel] | None = None
    include_croqui_warning: bool = False
    raster_b64: str | None = Field(default=None, max_length=12000000)
    raster_source: str | None = Field(default=None, max_length=250)
    title: str = Field(default="Área analisada", max_length=180)
    plant_heading: str = Field(default="PLANTA GEORREFERENCIADA", max_length=150)
    memorial_heading: str = Field(default="MEMORIAL DESCRITIVO", max_length=150)
    paper_format: str = Field(default="A4", pattern="^(A4|A3|A2|A1|A0)$")
    orientation: str = Field(default="paisagem", pattern="^(paisagem|retrato)$")
    layout_template: str = Field(default="lateral", pattern="^(lateral|inferior|classic_lateral|cartographic_frame|modern_lateral)$")
    scale_denominator: int | None = Field(default=None, ge=50, le=1000000)
    owner_rg: str | None = Field(default=None, max_length=60)
    owner_cpf: str | None = Field(default=None, max_length=25)
    property_address: str | None = Field(default=None, max_length=350)
    owner_name: str | None = Field(default=None, max_length=255)
    property_metadata: dict[str, str] | None = None
    responsible_name: str | None = Field(default=None, max_length=255)
    vertex_prefix: str = Field(default="V", min_length=1, max_length=8)
    professional_override: ProfessionalDocumentOverride | None = None
    edited_memorial: str | None = Field(default=None, max_length=100000)
    plant_elements: PlantElements = Field(default_factory=PlantElements)
    magnetic_declination_degrees: float | None = Field(default=None, ge=-30, le=30)
    survey_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


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


class ExportPolygonRequest(BaseModel):
    geometry: dict[str, Any]
    filename: str = Field(default="poligono", min_length=1, max_length=180)
    format: str = Field(pattern="^(txt|kml|shp)$")
    vertex_names: list[str] | None = None
    utm_zone: int | None = Field(default=None, ge=1, le=60)
    hemisphere: str | None = Field(default=None, pattern="^[NS]$")


@router.post("/export-polygon")
def download_polygon(payload: ExportPolygonRequest):
    try:
        data, filename, media_type = export_polygon(
            geometry=payload.geometry,
            filename=payload.filename,
            format=payload.format,
            names=payload.vertex_names,
            utm_zone=payload.utm_zone,
            hemisphere=payload.hemisphere,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


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
        if frame.empty:
            raise HTTPException(422, "O arquivo não contém geometria válida após a conversão.")

        # A geometria importada é usada como objeto de análise. Quando o
        # arquivo possui várias feições poligonais, consolidamos todas em uma
        # única geometria (Polygon/MultiPolygon) para que mapa, métricas,
        # análise, Snap e documentos usem exatamente o mesmo objeto.
        geometry_types = set(frame.geometry.geom_type.astype(str))
        if geometry_types.issubset({"Polygon", "MultiPolygon"}):
            merged = frame.geometry.union_all()
            output = gpd.GeoDataFrame(
                [{"source_features": int(len(frame))}],
                geometry=[merged],
                crs="EPSG:4674",
            )
            return json.loads(output.to_json(drop_id=False))

        if len(frame) > 1:
            raise HTTPException(
                422,
                "Arquivos com múltiplas feições não poligonais devem ser separados antes da importação para análise.",
            )

        return json.loads(frame.to_json(drop_id=False))


@router.post("/memorial-draft")
def memorial_draft(
    payload: MemorialRequest,
    user: User = Depends(get_current_user),
):
    if payload.parcels:
        try:
            prepared = prepare_parcels([item.model_dump() for item in payload.parcels])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {
            "title": payload.title,
            "area_hectares": round(sum(p.area_ha for p in prepared), 4),
            "perimeter_meters": round(sum(p.perimeter for p in prepared), 3),
            "parcel_count": len(prepared),
            "memorial_text": build_joint_memorial(
                prepared, title=payload.title, owner=payload.owner_name,
                responsible=payload.responsible_name,
                croqui=payload.include_croqui_warning,
                professional=_document_professional(user, payload),
                owner_rg=payload.owner_rg,
                owner_cpf=payload.owner_cpf,
                property_address=payload.property_address,
                memorial_heading=payload.memorial_heading,
                property_metadata=payload.property_metadata,
            ),
            "ai_used": False,
            "calculation_engine": "pyproj.Geod/GRS80",
        }
    if payload.geometry is None:
        raise HTTPException(422, "Selecione ao menos uma área para o memorial.")
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



class DocumentTemplateUpdate(BaseModel):
    company_name: str | None = Field(default=None, max_length=255)
    cnpj: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=500)
    email: str | None = Field(default=None, max_length=320)
    responsible_name: str | None = Field(default=None, max_length=255)
    responsible_registration: str | None = Field(default=None, max_length=120)
    document_footer: str | None = Field(default=None, max_length=500)


@router.get("/document-template")
def get_document_template():
    return load_document_template()


@router.put(
    "/document-template",
    dependencies=[Depends(require_permission("users.manage"))],
)
def update_document_template(payload: DocumentTemplateUpdate):
    return save_document_template(payload.model_dump(exclude_none=True))


@router.post(
    "/document-template/logo",
    dependencies=[Depends(require_permission("users.manage"))],
)
def upload_document_logo(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    raw = file.file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(413, "A logomarca deve possuir no máximo 5 MB.")
    try:
        path = save_document_logo(raw, suffix)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"logo_path": path, "template": load_document_template()}


@router.post("/memorial/docx")
def memorial_word(payload: MemorialRequest, user: User = Depends(get_current_user)):
    raw = ([item.model_dump() for item in payload.parcels] if payload.parcels
           else ([{"name": payload.title, "geometry": payload.geometry}] if payload.geometry else []))
    if not raw:
        raise HTTPException(422, "Selecione pelo menos uma área para o memorial.")
    try:
        from app.services.plant_croqui_warning import remove_optional_warnings
        parcels = prepare_parcels(raw)
        profile = _document_professional(user, payload)
        contents = build_memorial_docx(
            parcels=parcels,
            title=payload.title,
            memorial_heading=payload.memorial_heading,
            owner_name=payload.owner_name,
            owner_rg=payload.owner_rg,
            owner_cpf=payload.owner_cpf,
            property_address=payload.property_address,
            professional=profile,
            include_warning=payload.include_croqui_warning,
            property_metadata=payload.property_metadata,
            edited_memorial=remove_optional_warnings(
                payload.edited_memorial, payload.include_croqui_warning
            ),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return Response(
        content=contents,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="amazonika-memorial.docx"',
                 "Cache-Control": "private, no-store"},
    )


def _generated_documents_dir() -> Path:
    directory = get_settings().storage_dir / "generated_documents"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


@router.get("/documents/{document_id}")
def download_saved_document(
    document_id: UUID,
    user: User = Depends(get_current_user),
):
    directory = _generated_documents_dir()
    stem = document_id.hex
    file_path = directory / f"{stem}.pdf"
    meta_path = directory / f"{stem}.json"
    if not file_path.is_file() or not meta_path.is_file():
        raise HTTPException(404, "Documento não encontrado.")
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    # O QR não é autorização pública. É necessário login e pertencer ao
    # responsável pela emissão ou ter perfil administrador.
    is_admin = any(role.code == "ADMINISTRADOR" for role in user.roles)
    if metadata.get("user_id") != str(user.id) and not is_admin:
        raise HTTPException(403, "Documento pertence a outro usuário.")
    return Response(
        content=file_path.read_bytes(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="amazonika-documento-{stem[:12]}.pdf"',
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/plant-memorial/pdf")
def plant_memorial_pdf(
    payload: MemorialRequest,
    user: User = Depends(get_current_user),
):
    raw_parcels = (
        [parcel.model_dump() for parcel in payload.parcels]
        if payload.parcels else (
            [{"name": payload.title, "geometry": payload.geometry}]
            if payload.geometry else []
        )
    )
    if not raw_parcels:
        raise HTTPException(422, "Selecione ao menos uma área para a planta.")
    try:
        prepared = prepare_parcels(raw_parcels)
        is_preliminary = any(p.is_preliminary for p in (payload.parcels or []))
        document_id = uuid4()
        site = get_settings().public_base_url.rstrip("/")
        download_url = f"{site}/documentos/{document_id}"
        professional = _document_professional(user, payload)
        pdf, page_name, scale = make_joint_pdf(
            parcels=prepared,
            title=payload.title,
            owner_name=payload.owner_name,
            owner_rg=payload.owner_rg,
            owner_cpf=payload.owner_cpf,
            property_address=payload.property_address,
            responsible_name=professional.get("full_name") or user.full_name,
            professional=professional,
            croqui=payload.include_croqui_warning,
            raster_b64=payload.raster_b64,
            raster_source=payload.raster_source,
            plant_heading="PLANTA PRELIMINAR - NAO CERTIFICADA" if is_preliminary else payload.plant_heading,
            memorial_heading="MEMORIAL PRELIMINAR - NAO CERTIFICADO" if is_preliminary else payload.memorial_heading,
            qr_url=download_url,
            paper_format=payload.paper_format,
            layout_template=payload.layout_template,
            scale_denominator=payload.scale_denominator,
            orientation=payload.orientation,
            edited_memorial=payload.edited_memorial,
            plant_elements=payload.plant_elements.model_dump(),
            magnetic_declination_degrees=payload.magnetic_declination_degrees,
            survey_date=payload.survey_date,
            property_metadata=payload.property_metadata,
        )
        if is_preliminary or "PRELIMINAR" in payload.plant_heading.upper():
            pdf = stamp_preliminary_pdf(pdf)
        folder = _generated_documents_dir()
        stem = document_id.hex
        destination = folder / f"{stem}.pdf"
        metadata = folder / f"{stem}.json"
        temporary = folder / f"{stem}.tmp"
        temporary.write_bytes(pdf)
        os.replace(temporary, destination)
        metadata.write_text(
            json.dumps({"user_id": str(user.id), "document_id": str(document_id),
                        "title": payload.title}, ensure_ascii=False),
            encoding="utf-8",
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, f"Não foi possível gerar a prancha: {str(exc)[:500]}") from exc
    safe_name = "".join(
        char if char.isalnum() or char in {"-", "_"} else "-"
        for char in payload.title.strip()
    ).strip("-") or "planta"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name[:80]}-planta-memorial.pdf"',
            "Cache-Control": "private, no-store",
            "X-Page-Format": page_name,
            "X-Map-Scale": str(scale),
            "X-Document-Id": str(document_id),
        },
    )
