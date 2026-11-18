"""Rascunhos das peças técnicas, isolados pelo usuário autenticado."""
from __future__ import annotations

from uuid import UUID
from datetime import datetime, timezone
from fastapi.responses import FileResponse
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Response, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.auth import User
from app.models.technical_piece import TechnicalPiece
from app.services.auth import get_current_user, require_permission
from app.services.audit import write_audit
from app.services.ps4_validation import PS4Submission, evaluate_verified_ps4
from app.services.inpe_ps4_import import (
    fetch_inpe_item, examine_inpe_item, verified_official_xml_path,
)
from app.services.ps4_inpe_queue import new_job, save_job, read_job, safe_status, ACTIVE
from app.services.ps4_assets import store_uploaded_asset, stored_file_path, exists_matching
from app.services.ps4_tiles import mercator_tile_bounds, tile_intersects_footprint, render_png_tile, transparent_png_tile
from app.services.technical_import import parse_sigef_ods
from app.services.topcon_import import parse_topcon_report, MAX_BYTES
from app.services.topcon_perimeter_review import review_topcon_perimeter
from app.services.sigef_parcel_review import review_sigef_parcels
from app.services.sigef_ods_reviewed import build_reviewed_sigef_ods
from app.services.ps1_persistence import same_perimeter
from app.services.sigef_ods import _template_path
from app.services.sigef_ods_working import build_working_sigef_ods
from app.services.vertical_datum import convert_altitudes
from app.services.pa2_intersection import intersect_pa2
from app.services.constructed_vertices import calculate_constructed_vertex
from app.services.pa2_support_line import pa2_support_line

router = APIRouter(
    prefix="/technical-pieces", tags=["Peças técnicas"],
    dependencies=[Depends(require_permission("analysis.execute"))],
)


class PieceInput(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    snapshot: dict = Field(default_factory=dict)


def _view(piece: TechnicalPiece) -> dict:
    return {
        "id": str(piece.id), "title": piece.title, "status": piece.status,
        "created_at": piece.created_at.isoformat() if piece.created_at else None,
        "updated_at": piece.updated_at.isoformat() if piece.updated_at else None,
    }


def _owned(piece_id: UUID, db: Session, user: User) -> TechnicalPiece:
    piece = db.scalar(select(TechnicalPiece).where(
        TechnicalPiece.id == piece_id,
        TechnicalPiece.user_id == user.id,
    ))
    if piece is None:
        raise HTTPException(404, "Peça técnica não encontrada.")
    return piece



class ParcelMetricsInput(BaseModel):
    parcels: list[dict] = Field(min_length=1, max_length=100)


@router.post("/parcel-metrics")
def parcel_metrics(payload: ParcelMetricsInput, user: User = Depends(get_current_user)):
    """Mesma preparação de parcelas usada pelos documentos técnicos."""
    from app.services.plant_memorial_v2 import prepare_parcels
    try:
        parcels = prepare_parcels(payload.parcels)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"parcels": [{"area_ha": p.area_ha, "perimeter_m": p.perimeter,
                         "metrics_method": p.metrics_method} for p in parcels]}


@router.post("/import-topcon")
def import_topcon(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Extrai relatório GNSS para revisão, sem cadastrar perímetro ou certificar."""
    filename = file.filename or ""
    if not filename.lower().endswith((".htm", ".html", ".xlsx", ".pdf")):
        raise HTTPException(422, "Envie relatório TOPCON HTML, HTM, XLSX ou PDF.")
    raw = file.file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "Relatório maior que 12 MB.")
    try:
        return parse_topcon_report(raw, filename)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class TopconPerimeterReviewInput(BaseModel):
    points: list[dict] = Field(default_factory=list, max_length=5000)


@router.post("/topcon/perimeter-review")
def review_topcon_perimeter_route(
    payload: TopconPerimeterReviewInput,
    user: User = Depends(get_current_user),
):
    """Revisão técnica de perímetro; não cria ODS nem altera peças salvas."""
    return review_topcon_perimeter(payload.points)


class Pa2IntersectionInput(BaseModel):
    witnesses: list[dict] = Field(min_length=4, max_length=4)
    utm_zone: int | None = None
    hemisphere: str | None = None
    sirgas2000_confirmed: bool = False


@router.post("/topcon/pa2-intersection")
def calculate_pa2_intersection(
    payload: Pa2IntersectionInput,
    user: User = Depends(get_current_user),
):
    """Interseção de retas com quatro testemunhos; não confirma h ou precisão."""
    try:
        return intersect_pa2(
            payload.witnesses,
            utm_zone=payload.utm_zone,
            hemisphere=payload.hemisphere,
            sirgas2000_confirmed=payload.sirgas2000_confirmed,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class Pa2SupportLineInput(BaseModel):
    supports: list[dict] = Field(min_length=2, max_length=2)
    hint_longitude: float
    hint_latitude: float
    utm_zone: int
    hemisphere: str
    sirgas2000_confirmed: bool
    altitude_type: str


@router.post("/topcon/pa2-support-line")
def calculate_pa2_support_line_route(
    payload: Pa2SupportLineInput,
    user: User = Depends(get_current_user),
):
    """Inserção provisória no alinhamento de dois marcos, com altitude HN/H."""
    try:
        return pa2_support_line(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class ConstructedVertexInput(BaseModel):
    method: str
    witnesses: list[dict] = Field(min_length=2, max_length=2)
    distance_m: float
    side: str
    hint_longitude: float | None = None
    hint_latitude: float | None = None
    utm_zone: int | None = None
    hemisphere: str | None = None
    sirgas2000_confirmed: bool = False


@router.post("/topcon/constructed-vertex")
def calculate_constructed_vertex_route(
    payload: ConstructedVertexInput,
    user: User = Depends(get_current_user),
):
    """Pré-cálculo PA1/PT8. Nunca presume h, precisões ou certificação."""
    try:
        return calculate_constructed_vertex(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class SigefParcelReviewInput(BaseModel):
    identification: dict = Field(default_factory=dict)
    parcels: list[dict] = Field(default_factory=list, max_length=50)
    neighbors: list[dict] = Field(default_factory=list, max_length=200)


@router.post("/sigef/parcels-review")
def review_sigef_parcels_route(
    payload: SigefParcelReviewInput,
    user: User = Depends(get_current_user),
):
    """Validação preliminar: nunca modifica vértices nem certifica parcelas."""
    try:
        return review_sigef_parcels(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class VerticalConversionInput(BaseModel):
    points: list[dict] = Field(default_factory=list, max_length=5000)
    model: str = "hgeoHNOR2020"


@router.post("/topcon/vertical-conversion")
def convert_topcon_vertical(
    payload: VerticalConversionInput,
    user: User = Depends(get_current_user),
):
    """Converte h para HN/H com fator informado; SIGEF permanece h."""
    try:
        return convert_altitudes(payload.points, model=payload.model)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class ReviewedSigefOdsInput(BaseModel):
    piece_id: UUID | None = None
    identification: dict = Field(default_factory=dict)
    parcels: list[dict] = Field(default_factory=list, max_length=50)
    neighbors: list[dict] = Field(default_factory=list, max_length=200)


@router.post("/sigef/rascunho-ods")
def download_working_sigef_ods(
    payload: ReviewedSigefOdsInput,
    user: User = Depends(get_current_user),
):
    """Planilha de trabalho marcada INCOMPLETA; nunca suplanta validação SIGEF."""
    try:
        data = build_working_sigef_ods(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return Response(
        content=data,
        media_type="application/vnd.oasis.opendocument.spreadsheet",
        headers={
            "Content-Disposition": 'attachment; filename="RASCUNHO_INCOMPLETO_NAO_SUBMETER_SIGEF.ods"',
            "Cache-Control": "private, no-store",
            "X-Sigef-Validation": "RASCUNHO_NAO_SUBMETER",
        },
    )


@router.get("/sigef/modelo-ods")
def download_sigef_model(
    user: User = Depends(get_current_user),
):
    """Official blank ODS template; never fills missing heights or sigmas."""
    source = _template_path()
    if not source.is_file():
        raise HTTPException(503, "Modelo ODS SIGEF não disponível.")
    data = source.read_bytes()
    return Response(
        content=data,
        media_type="application/vnd.oasis.opendocument.spreadsheet",
        headers={
            "Content-Disposition": 'attachment; filename="MODELO_SIGEF_EM_BRANCO.ods"',
            "Cache-Control": "private, no-store",
            "X-Sigef-Validation": "MODELO_NAO_PREENCHIDO",
        },
    )


@router.post("/sigef/reviewed-ods")
def export_reviewed_sigef_ods(
    payload: ReviewedSigefOdsInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Exporta ODS para conferência técnica, não certificação oficial."""
    approved = []
    approved_pb1 = []
    if payload.piece_id is not None:
        piece = _owned(payload.piece_id, db, user)
        state = (piece.snapshot or {}).get("ps1") or {}
        approval = state.get("approval") or {}
        assets = state.get("assets") or {}
        if approval.get("status") == "APPROVED_BY_RT" and all(
            approval.get("hashes", {}).get(k) == (assets.get(k) or {}).get("sha256")
            and exists_matching(user.id, piece.id, assets.get(k) or {})
            for k in ("ps1_ortho", "ps1_dtm", "ps1_report")
        ):
            calculation = state.get("calculation") or {}
            expected = calculation.get("vertices") or []
            ps1_parcels = [p for p in payload.parcels if any(
                v.get("sigef_method") == "PS1" for v in (p.get("vertices") or []))]
            if len(ps1_parcels) == 1 and same_perimeter(expected, ps1_parcels[0]["vertices"]):
                approved = calculation.get("generated") or []
        pb = (piece.snapshot or {}).get("pb1") or {}
        decision = pb.get("approval") or {}
        attached = pb.get("assets") or {}
        hashes = decision.get("hashes") or {}
        if (decision.get("status") == "APPROVED_BY_RT" and "pb1_dtm" in hashes
                and hashes == {k:v["sha256"] for k,v in attached.items() if k in ("pb1_dtm","pb1_color")}
                and all(exists_matching(user.id,piece.id,attached[k]) for k in hashes)):
            parcels_pb1 = [p for p in payload.parcels if any(v.get("sigef_method")=="PB1" for v in p.get("vertices",[]))]
            if len(parcels_pb1)==1 and same_perimeter(decision.get("vertices"),parcels_pb1[0]["vertices"]):
                approved_pb1 = decision.get("generated") or []
    try:
        data = build_reviewed_sigef_ods(payload.model_dump(), approved_ps1_vertices=approved, approved_pb1_vertices=approved_pb1)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return Response(
        content=data,
        media_type="application/vnd.oasis.opendocument.spreadsheet",
        headers={
            "Content-Disposition": 'attachment; filename="SIGEF_PREVALIDACAO_AMAZONIKA.ods"',
            "Cache-Control": "no-store",
            "X-Sigef-Validation": "PREVALIDACAO_LOCAL",
        },
    )


@router.post("/import-sigef-ods")
def import_sigef_ods(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Valida e converte ODS SIGEF para GeoJSON completo. Não grava rascunho sem revisão."""
    if not (file.filename or "").lower().endswith(".ods"):
        raise HTTPException(422, "Envie uma planilha .ods do SIGEF.")
    raw = file.file.read(15 * 1024 * 1024 + 1)
    if len(raw) > 15 * 1024 * 1024:
        raise HTTPException(413, "Arquivo ODS maior que 15 MB.")
    try:
        return parse_sigef_ods(raw)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("")
def list_pieces(
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    results = db.scalars(
        select(TechnicalPiece).where(TechnicalPiece.user_id == user.id)
        .order_by(TechnicalPiece.updated_at.desc())
        .limit(200)
    ).all()
    return [_view(piece) for piece in results]


def _validated_snapshot(
    incoming: dict, piece: TechnicalPiece | None, user: User
) -> dict:
    """Preserva anexos confiáveis e recalcula os resultados a cada gravação."""
    snapshot = dict(incoming)
    # PS1: somente anexos e aprovação produzidos pelo servidor são confiáveis.
    prior = (piece.snapshot or {}) if piece else {}
    previous_ps1 = prior.get("ps1") or {}
    snapshot["ps1"] = {"assets": previous_ps1.get("assets", {})}
    if ((snapshot.get("topcon") or {}).get("boundary") ==
            (prior.get("topcon") or {}).get("boundary") and
            snapshot.get("features") == prior.get("features") and previous_ps1.get("calculation")):
        snapshot["ps1"] = previous_ps1
    # A primeira adoção da poligonal calculada pode alterar features e boundary
    # sem alterar os atributos técnicos aprovados. Compare o perímetro inteiro.
    elif previous_ps1.get("approval") and previous_ps1.get("calculation"):
        expected = previous_ps1["calculation"].get("vertices") or []
        actual = (snapshot.get("topcon") or {}).get("boundary") or []
        if same_perimeter(expected, actual):
            snapshot["ps1"] = previous_ps1
    # PB1 utiliza ativos privados independentes do PS4. Cliente não pode
    # substituir metadados confiáveis do upload nem forjar aprovação.
    old_pb1 = ((piece.snapshot or {}).get("pb1") or {}) if piece else {}
    trusted_assets = old_pb1.get("assets", {})
    snapshot["pb1"] = {
        "assets": trusted_assets,
        "review_status": "PRELIMINARY",
    }
    # Não aceitar pontos PB1 de outra cena, fora do GeoTIFF vinculado,
    # nem resultados de aprovação autodeclarados pelo navegador.
    pb1_points = ((snapshot.get("topcon") or {}).get("pb1_draft") or [])
    if pb1_points:
        official_color = (trusted_assets.get("pb1_color") or {}).get("sha256")
        official_dtm = (trusted_assets.get("pb1_dtm") or {}).get("sha256")
        if not official_dtm:
            raise HTTPException(422, "Vértices PB1 requerem MDT numérico vinculado no servidor.")
        if len(pb1_points) > 5000:
            raise HTTPException(422, "Limite de 5000 vértices PB1 excedido.")
        for point in pb1_points:
            if not isinstance(point, dict) or point.get("raster_sha256") not in {h for h in (official_color, official_dtm) if h}:
                raise HTTPException(422, "Vértice PB1 vinculado a outro GeoTIFF. Refaça a captura.")
            if not isinstance(point.get("name"), str) or not point["name"].strip():
                raise HTTPException(422, "Código de vértice PB1 inválido.")
            if not all(isinstance(point.get(key), (int, float)) and
                       not isinstance(point.get(key), bool) and
                       float("-inf") < point[key] < float("inf")
                       for key in ("longitude", "latitude")):
                raise HTTPException(422, "Coordenada PB1 inválida.")
            if not (-180 <= point["longitude"] <= 180 and -90 <= point["latitude"] <= 90):
                raise HTTPException(422, "Vértice PB1 fora de longitude/latitude WGS84.")
    record = old_pb1.get("ibge_factors")
    if record and record.get("points") == [{"name":p["name"],"latitude":p["latitude"],"longitude":p["longitude"]} for p in pb1_points]:
        snapshot["pb1"]["ibge_factors"] = record
    # Only server-calculated results survive; invalidate on any source or geometry change.
    prior_snapshot = (piece.snapshot or {}) if piece else {}
    relevant_pb1 = ("pb1_draft", "pb1_source", "boundary")
    if piece and all((snapshot.get("topcon") or {}).get(k) ==
                     (prior_snapshot.get("topcon") or {}).get(k) for k in relevant_pb1):
        if old_pb1.get("partial_preview"):
            snapshot["pb1"]["partial_preview"] = old_pb1["partial_preview"]
        if old_pb1.get("technical_preview"):
            snapshot["pb1"]["technical_preview"] = old_pb1["technical_preview"]
        if (old_pb1.get("approval") and snapshot.get("features") == prior_snapshot.get("features")
                and (snapshot.get("topcon") or {}).get("pb1_closure") == (prior_snapshot.get("topcon") or {}).get("pb1_closure")):
            snapshot["pb1"]["approval"] = old_pb1["approval"]
            snapshot["pb1"]["review_status"] = "APPROVED_BY_RT"
    previous = (piece.snapshot or {}).get("ps4", {}) if piece else {}
    same_checkpoint_geometry = bool(
        piece is not None and
        snapshot.get("features") == (piece.snapshot or {}).get("features") and
        (snapshot.get("topcon") or {}).get("ps4_draft") ==
        ((piece.snapshot or {}).get("topcon") or {}).get("ps4_draft") and
        (snapshot.get("topcon") or {}).get("ps4_selected_scene") ==
        ((piece.snapshot or {}).get("topcon") or {}).get("ps4_selected_scene")
    )
    if "ps4" not in snapshot and previous:
        # Salvamentos de texto/layout não podem revogar uma decisão PS4 válida.
        # Qualquer alteração do traçado ou metadados geoespaciais revoga
        # a aprovação e obriga nova conferência do responsável técnico.
        old_snapshot = piece.snapshot or {} if piece else {}
        relevant_topcon = (
            "boundary", "ps4_draft", "ps4_selected_scene",
            "ps4_ortho_report", "ps4_quality", "construction_skipped",
            "ps4_closure",
        )
        current_topcon = snapshot.get("topcon") or {}
        old_topcon = old_snapshot.get("topcon") or {}
        same_geometry = (
            piece is not None
            and snapshot.get("features") == old_snapshot.get("features")
            and all(
                current_topcon.get(key) == old_topcon.get(key)
                for key in relevant_topcon
            )
        )
        if same_geometry and (previous.get("approval") or previous.get("completed_at")):
            snapshot["ps4"] = previous
            return snapshot
        snapshot["ps4"] = previous
    if "ps4" not in snapshot:
        return snapshot
    requested = snapshot["ps4"]
    if not isinstance(requested, dict):
        raise HTTPException(422, "Estrutura PS4 inválida.")
    # Upload pode preceder o preenchimento; preserva o anexo do banco.
    if "submission" not in requested:
        if piece and isinstance(previous, dict) and "submission" not in previous:
            # A cena pode ter sido importada antes da entrega do PDF.
            # Salvar o desenho preliminar não deve apagar a proveniência INPE,
            # a fila de importação nem os anexos privados já associados.
            # Descartar checagens antigas sempre que a geometria ou cena mudar.
            snapshot["ps4"] = {
                "assets": previous.get("assets", {}),
                **({"source_provenance": previous["source_provenance"]}
                   if previous.get("source_provenance") else {}),
                **({"import_job_id": previous["import_job_id"]}
                   if previous.get("import_job_id") else {}),
                **({"checkpoint_analysis": previous["checkpoint_analysis"]}
                   if same_checkpoint_geometry and previous.get("checkpoint_analysis") and
                      previous["checkpoint_analysis"].get("raster_sha256") ==
                      (previous.get("assets", {}).get("raster") or {}).get("sha256")
                   else {}),
            }
            return snapshot
        raise HTTPException(422, "Formulário PS4 não informado.")
    try:
        submitted = PS4Submission.model_validate(requested["submission"])
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, "Dados PS4 inválidos no snapshot.") from exc
    # Arquivos já associados são sempre obtidos do banco, nunca do payload.
    assets = previous.get("assets", {}) if isinstance(previous, dict) else {}
    if not piece:
        validation = evaluate_verified_ps4(submitted, {}, user.id, UUID(int=0))
    else:
        validation = evaluate_verified_ps4(submitted, assets, user.id, piece.id)
    preserved_source = previous.get("source_provenance") if isinstance(previous, dict) else None
    if preserved_source and (
        assets.get("raster", {}).get("sha256") !=
        (previous.get("assets", {}).get("raster") or {}).get("sha256")
    ):
        preserved_source = None
    snapshot["ps4"] = {
        "submission": submitted.model_dump(mode="json"),
        "assets": assets,
        "validation": validation,
        **({"checkpoint_analysis": previous["checkpoint_analysis"]}
           if previous.get("checkpoint_analysis") and
              previous["checkpoint_analysis"].get("raster_sha256") ==
              (assets.get("raster") or {}).get("sha256") and
              same_checkpoint_geometry
           else {}),
        **({"source_provenance": preserved_source} if preserved_source else {}),
        **({"import_job_id": previous["import_job_id"]}
           if isinstance(previous, dict) and previous.get("import_job_id") else {}),
    }
    return snapshot



class PB1SheetLookupInput(BaseModel):
    geometry: dict


@router.post("/pb1/sheets/lookup")
def pb1_sheet_lookup(
    payload: PB1SheetLookupInput,
    user: User = Depends(get_current_user),
):
    """Consulta de articulação sem gravar ou validar certificação."""
    from app.services.pb1_articulation import identify_pb1_sheets

    try:
        return identify_pb1_sheets(payload.geometry)
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("", status_code=201)
def create_piece(
    payload: PieceInput,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    snapshot = _validated_snapshot(payload.snapshot, None, user)
    piece = TechnicalPiece(user_id=user.id, title=payload.title, snapshot=snapshot)
    db.add(piece)
    db.commit()
    db.refresh(piece)
    return {**_view(piece), "snapshot": piece.snapshot}


@router.get("/{piece_id}")
def get_piece(
    piece_id: UUID,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    piece = _owned(piece_id, db, user)
    return {**_view(piece), "snapshot": piece.snapshot}


@router.put("/{piece_id}")
def update_piece(
    piece_id: UUID, payload: PieceInput,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    piece = _owned(piece_id, db, user)
    piece.title = payload.title
    piece.snapshot = _validated_snapshot(payload.snapshot, piece, user)
    piece.status = "DRAFT"
    db.commit()
    db.refresh(piece)
    return {**_view(piece), "snapshot": piece.snapshot}


@router.delete("/{piece_id}", status_code=204)
def delete_piece(
    piece_id: UUID,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    db.delete(_owned(piece_id, db, user))
    db.commit()


@router.put("/{piece_id}/ps4")
def save_ps4(
    piece_id: UUID, payload: PS4Submission,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    piece = _owned(piece_id, db, user)
    snapshot = dict(piece.snapshot or {})
    snapshot["ps4"] = {"submission": payload.model_dump(mode="json")}
    piece.snapshot = _validated_snapshot(snapshot, piece, user)
    piece.status = "DRAFT"
    db.commit()
    db.refresh(piece)
    return {"piece_id": str(piece.id), "ps4": piece.snapshot["ps4"]}


@router.get("/{piece_id}/ps4")
def get_ps4(
    piece_id: UUID,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    piece = _owned(piece_id, db, user)
    current = (piece.snapshot or {}).get("ps4") or {}
    return {
        "submission": current.get("submission", {
            "needs_additional_vertices": True, "vertices": [],
        }),
        "assets": current.get("assets", {}),
        "approval": current.get("approval"),
        "completed_at": current.get("completed_at"),
        "source_provenance": current.get("source_provenance"),
        "import_job_id": current.get("import_job_id"),
        "checkpoint_analysis": current.get("checkpoint_analysis"),
        "validation": current.get("validation", {
            "status": "BLOCKED",
            "blockers": ["Validação PS4 não iniciada."],
            "requires_rt_review": True,
        }),
    }



@router.post("/{piece_id}/pb1/files/{kind}")
def upload_pb1_file(
    piece_id: UUID, kind: str, file: UploadFile = File(...),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """GeoTIFF oficial PB1, separado de PS4. Recortes limitados a 256 MiB."""
    piece = _owned(piece_id, db, user)
    if kind not in ("pb1_color", "pb1_dtm"):
        raise HTTPException(422, "Tipo PB1 inválido.")
    if not (file.filename or "").lower().endswith((".tif", ".tiff")):
        raise HTTPException(422, "Envie GeoTIFF georreferenciado.")
    try:
        record = store_uploaded_asset(file.file, user.id, piece.id, kind)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    snapshot = dict(piece.snapshot or {})
    pb1 = dict(snapshot.get("pb1") or {})
    assets = dict(pb1.get("assets") or {})
    assets[kind] = record
    pb1["assets"] = assets
    if kind == "pb1_color":
        # Troca da ortoimagem invalida somente o traçado PB1, não o PS4.
        topcon = dict(snapshot.get("topcon") or {})
        topcon["pb1_draft"] = []
        topcon["pb1_closure"] = {"start": "", "confirmed": False, "signature": ""}
        snapshot["topcon"] = topcon
    elif kind == "pb1_dtm":
        topcon = dict(snapshot.get("topcon") or {})
        if isinstance(topcon.get("pb1_draft"), list):
            topcon["pb1_draft"] = [
                {**p, "source_elevation_m": None}
                for p in topcon["pb1_draft"] if isinstance(p, dict)
            ]
            topcon["pb1_closure"] = {"start": "", "confirmed": False, "signature": ""}
            snapshot["topcon"] = topcon
    pb1["review_status"] = "PRELIMINARY"
    pb1.pop("approval", None)
    pb1.pop("technical_preview", None)
    pb1.pop("partial_preview", None)
    snapshot["pb1"] = pb1
    piece.snapshot = snapshot
    db.add(piece)
    db.commit()
    db.refresh(piece)
    return {"piece_id": str(piece.id), "asset": record}


@router.get("/{piece_id}/pb1/assets")
def get_pb1_assets(
    piece_id: UUID, db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    piece = _owned(piece_id, db, user)
    pb1 = (piece.snapshot or {}).get("pb1") or {}
    return {"assets": pb1.get("assets") or {}, "review_status": "PRELIMINARY"}


@router.get("/{piece_id}/pb1/raster/tiles/{kind}/{digest}/{z}/{x}/{y}.png")
def pb1_raster_tile(
    piece_id: UUID, kind: str, digest: str, z: int, x: int, y: int,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """Tiles privados para conferir o produto oficial, sem fallback orbital."""
    if kind not in ("pb1_color", "pb1_dtm"):
        raise HTTPException(422, "Produto PB1 inválido.")
    piece = _owned(piece_id, db, user)
    asset = (((piece.snapshot or {}).get("pb1") or {}).get("assets") or {}).get(kind)
    if not isinstance(asset, dict) or asset.get("sha256") != digest:
        raise HTTPException(404, "Produto PB1 não vinculado à peça.")
    try:
        mercator_tile_bounds(z, x, y)
        path = stored_file_path(user.id, piece.id, kind, digest)
        if not path.is_file():
            raise HTTPException(404, "Produto raster PB1 não encontrado.")
        if not tile_intersects_footprint(asset.get("metadata") or {}, z, x, y):
            return Response(transparent_png_tile(), media_type="image/png",
                            headers={"Cache-Control": "private, max-age=3600"})
        png = render_png_tile(path, z, x, y, mode=kind)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return Response(png, media_type="image/png",
                    headers={"Cache-Control": "private, max-age=3600"})


class PB1DtmSampleInput(BaseModel):
    longitude: float
    latitude: float


@router.post("/{piece_id}/pb1/dtm/sample")
def sample_pb1_height(
    piece_id: UUID, payload: PB1DtmSampleInput,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    from app.services.pb1_dtm_sampling import sample_pb1_dtm
    piece = _owned(piece_id, db, user)
    asset = (((piece.snapshot or {}).get("pb1") or {}).get("assets") or {}).get("pb1_dtm")
    if not isinstance(asset, dict):
        raise HTTPException(422, "Importe primeiro o MDT numérico PB1.")
    path = stored_file_path(user.id, piece.id, "pb1_dtm", asset["sha256"])
    bands = (asset.get("metadata") or {}).get("bands") or [{}]
    nodata = bands[0].get("no_data_value")
    try:
        h_source = sample_pb1_dtm(path, payload.longitude, payload.latitude, nodata)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {
        "source_elevation_m": h_source,
        "raster_sha256": asset["sha256"],
        "vertical_datum": "UNVERIFIED",
        "h_ellipsoidal_m": None,
        "status": "PENDING_VERTICAL_DATUM",
        "notice": "Cota original amostrada. Confirme o datum vertical e a conversão para h.",
    }



@router.get("/{piece_id}/pb1/diagnostic")
def pb1_diagnostic(piece_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.services.pb1_diagnostic import compare_mdt_controls
    from app.services.pb1_dtm_sampling import sample_pb1_dtm
    piece = _owned(piece_id, db, user)
    snapshot = piece.snapshot or {}
    topcon = snapshot.get("topcon") or {}
    dtm = ((snapshot.get("pb1") or {}).get("assets") or {}).get("pb1_dtm")
    if not dtm:
        raise HTTPException(422, "Vincule o MDT numérico.")
    path = stored_file_path(user.id, piece.id, "pb1_dtm", dtm["sha256"])
    bands = (dtm.get("metadata") or {}).get("bands") or [{}]
    try:
        result = compare_mdt_controls(topcon.get("boundary") or [], topcon.get("vertical_calculated"),
            lambda lon, lat: sample_pb1_dtm(path, lon, lat, bands[0].get("no_data_value")))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {**result, "dtm_sha256": dtm["sha256"]}


class PB1TechnicalInput(BaseModel):
    vertical_kind: str
    vertical_datum: str
    vertical_reference: str
    accuracy_reference: str
    sigma_e_m: float
    sigma_n_m: float
    source_sigma_m: float
    limit_category: str
    factors: dict[str, list[float]] = Field(default_factory=dict)
    ibge_output: str = Field(default="", max_length=1000000)
    factor_reference: str = ""


@router.post("/{piece_id}/pb1/technical-preview")
def pb1_technical_preview(
    piece_id: UUID, payload: PB1TechnicalInput,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """Calcula prévia no servidor a partir dos V salvos e do MDT original."""
    from math import hypot, isfinite
    from app.services.pb1_vertical import PB1VerticalPoint, convert_pb1_height
    from app.services.pb1_dtm_sampling import sample_pb1_dtm
    piece = _owned(piece_id, db, user)
    snapshot = piece.snapshot or {}
    assets = (snapshot.get("pb1") or {}).get("assets") or {}
    dtm = assets.get("pb1_dtm")
    color = assets.get("pb1_color")
    points = (snapshot.get("topcon") or {}).get("pb1_draft") or []
    if not dtm or not points or not exists_matching(user.id, piece.id, dtm):
        raise HTTPException(422, "Salve os vértices PB1 e vincule o MDT numérico válido.")
    if len(points) > 500:
        raise HTTPException(422, "O cálculo preliminar aceita até 500 V por operação.")
    if not all(x.strip() for x in (payload.vertical_datum, payload.vertical_reference, payload.accuracy_reference)):
        raise HTTPException(422, "Informe documentação vertical e de exatidão horizontal.")
    if not all(isfinite(x) and x >= 0 for x in (payload.sigma_e_m, payload.sigma_n_m, payload.source_sigma_m)):
        raise HTTPException(422, "Sigmas devem ser finitos e não negativos.")
    if payload.sigma_e_m == 0 or payload.sigma_n_m == 0:
        raise HTTPException(422, "Informe incertezas horizontais documentadas, maiores que zero.")
    limits = {"NATURAL": 3.0, "INACCESSIBLE": 7.5, "ARTIFICIAL": 0.5}
    if payload.limit_category not in limits:
        raise HTTPException(422, "Classifique a acessibilidade e natureza do limite.")
    model = {"NORMAL": "HGEOHNOR2020", "ORTHOMETRIC": "MAPGEO2015", "ELLIPSOIDAL": "NONE"}.get(payload.vertical_kind)
    if not model:
        raise HTTPException(422, "Tipo de altitude não identificado.")
    source = (snapshot.get("topcon") or {}).get("pb1_source") or {}
    declared = str(source.get("source_model") or "").upper()
    if declared and declared not in ("OUTRO", model):
        raise HTTPException(422, "Modelo original incompatível com a conversão disponível; revise a documentação.")
    if source.get("vertical_kind") and source["vertical_kind"] != payload.vertical_kind:
        raise HTTPException(422, "Tipo vertical divergente do declarado na origem.")

    if model != "NONE" and not payload.factor_reference.strip():
        raise HTTPException(422, "Informe a origem dos fatores individuais do modelo.")
    if len({p["name"] for p in points}) != len(points):
        raise HTTPException(422, "Códigos PB1 repetidos.")
    factors = payload.factors
    if payload.ibge_output:
        if model != "HGEOHNOR2020":
            raise HTTPException(422, "O retorno hgeoHNOR2020 exige altura normal compatível.")
        from app.services.pb1_ibge import parse_ibge_output
        try:
            factors = parse_ibge_output(payload.ibge_output, points)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    path = stored_file_path(user.id, piece.id, "pb1_dtm", dtm["sha256"])
    bands = (dtm.get("metadata") or {}).get("bands") or [{}]
    output = []
    try:
        for point in points:
            if point.get("raster_sha256") not in {a["sha256"] for a in (color, dtm) if a}:
                raise ValueError("Vinculação raster alterada; revise o traçado.")
            name = point["name"]
            factor = factors.get(name)
            if model != "NONE" and (factor is None or len(factor) != 2):
                raise ValueError("Informe fator e sigma individual para " + name)
            value = sample_pb1_dtm(path, point["longitude"], point["latitude"], bands[0].get("no_data_value"))
            row = convert_pb1_height(PB1VerticalPoint(
                vertex_id=name, source_value_m=value, source_vertical_kind=payload.vertical_kind,
                source_vertical_datum=payload.vertical_datum, conversion_model=model,
                conversion_factor_m=factor[0] if model != "NONE" else None,
                source_sigma_m=payload.source_sigma_m,
                factor_sigma_m=factor[1] if model != "NONE" else None,
                raster_sha256=dtm["sha256"],
            ))
            output.append({**row, "latitude": point["latitude"], "longitude": point["longitude"],
                           "sigma_e_m": payload.sigma_e_m, "sigma_n_m": payload.sigma_n_m})
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    horizontal = hypot(payload.sigma_e_m, payload.sigma_n_m)
    result = {"points": output, "horizontal_sigma_m": horizontal,
            "limit_m": limits[payload.limit_category],
            "meets_numeric_threshold": horizontal <= limits[payload.limit_category],
            "accuracy_reference": payload.accuracy_reference,
            "vertical_reference": payload.vertical_reference,
            "factor_reference": payload.factor_reference,
            "status": "PRELIMINARY_RT_REVIEW",
            "notice": "Estimativa com parâmetros declarados; não comprova exatidão, datum ou aprovação RT."}
    result["inputs"] = payload.model_dump(exclude={"ibge_output"})
    result["inputs"]["factors"] = factors
    result["color_sha256"] = color["sha256"] if color else None
    result["dtm_sha256"] = dtm["sha256"]
    result["calculated_at"] = datetime.now(timezone.utc).isoformat()
    saved = dict(snapshot)
    saved["pb1"] = {**(snapshot.get("pb1") or {}), "technical_preview": result}
    piece.snapshot = saved
    db.commit()
    return result


class PB1PartialInput(BaseModel):
    sigma_e_m: float | None = Field(default=None, gt=0)
    sigma_n_m: float | None = Field(default=None, gt=0)
    source_sigma_m: float | None = Field(default=None, gt=0)


@router.post("/{piece_id}/pb1/process-partial")
def pb1_process_partial(piece_id: UUID, payload: PB1PartialInput,
    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.services.pb1_partial import partial_parameters, partial_vertex
    from app.services.pb1_dtm_sampling import sample_pb1_dtm
    from app.services.pb1_ibge import parse_ibge_output
    piece = _owned(piece_id, db, user)
    snapshot = dict(piece.snapshot or {})
    top = snapshot.get("topcon") or {}
    points = top.get("pb1_draft") or []
    pb = dict(snapshot.get("pb1") or {})
    assets = pb.get("assets") or {}
    color, dtm = assets.get("pb1_color"), assets.get("pb1_dtm")
    if not dtm or not points or len(points)>500 or not exists_matching(user.id, piece.id, dtm):
        raise HTTPException(422, "É necessário MDT numérico válido e de 1 a 500 vértices salvos.")
    source = top.get("pb1_source") or {}
    params = partial_parameters(source, payload.model_dump())
    factors = {}
    record = pb.get("ibge_factors") or {}
    if record.get("raw"):
        try:
            factors = parse_ibge_output(record["raw"], points)
            # Do not use factors from an unidentified or different grid.
            if not all(line.split()[-1].upper()=="HGEOHNOR_SANTANA" for line in record["raw"].splitlines() if line.strip()):
                factors = {}
        except ValueError:
            factors = {}
    path = stored_file_path(user.id,piece.id,"pb1_dtm",dtm["sha256"]) if dtm else None
    bands = ((dtm or {}).get("metadata") or {}).get("bands") or [{}]
    rows=[]
    for point in points:
        if point.get("raster_sha256") not in {a["sha256"] for a in (color, dtm) if a}:
            raise HTTPException(422,"Vértice vinculado a outro raster.")
        z=None
        error=None
        if path:
            try:
                z=sample_pb1_dtm(path,point["longitude"],point["latitude"],bands[0].get("no_data_value"))
            except (ValueError,RuntimeError) as exc:
                error=str(exc)
        row=partial_vertex(point,z,params,factors.get(point["name"]),source)
        if error or z is None:
            raise HTTPException(422, f"{point['name']}: MDT sem cota válida ({error or 'NoData'}).")
        rows.append(row)
    result={**params,"points":rows,"status":"PRELIMINARY_RT_REVIEW",
        "color_sha256":color["sha256"] if color else None,"dtm_sha256":dtm["sha256"],
        "calculated_at":datetime.now(timezone.utc).isoformat(),
        "notice":"Estimativas preliminares; não constituem exatidão comprovada nem aprovação RT."}
    pb.pop("approval", None)
    pb["review_status"] = "PRELIMINARY"
    pb["partial_preview"]=result
    snapshot["pb1"]=pb
    piece.snapshot=snapshot
    db.commit()
    return result


@router.get("/{piece_id}/pb1/process-partial")
def get_pb1_partial(piece_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    piece=_owned(piece_id,db,user)
    return {"preview":((piece.snapshot or {}).get("pb1") or {}).get("partial_preview")}


class PB1IbgeFactorsInput(BaseModel):
    ibge_output: str = Field(min_length=1, max_length=1000000)


@router.post("/{piece_id}/pb1/ibge-factors")
def save_pb1_ibge_factors(piece_id: UUID, payload: PB1IbgeFactorsInput,
    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.services.pb1_ibge import parse_ibge_output
    from hashlib import sha256
    piece = _owned(piece_id, db, user)
    snapshot = dict(piece.snapshot or {})
    points = (snapshot.get("topcon") or {}).get("pb1_draft") or []
    try:
        factors = parse_ibge_output(payload.ibge_output, points)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    record = {"factors": factors, "sha256": sha256(payload.ibge_output.encode()).hexdigest(),
        "points": [{"name":p["name"],"latitude":p["latitude"],"longitude":p["longitude"]} for p in points],
        "raw": payload.ibge_output, "status":"FACTORS_ONLY", "imported_at":datetime.now(timezone.utc).isoformat()}
    pb = dict(snapshot.get("pb1") or {})
    pb.pop("partial_preview",None)
    pb.pop("approval", None)
    pb["review_status"] = "PRELIMINARY"
    pb["ibge_factors"] = record
    snapshot["pb1"] = pb
    piece.snapshot = snapshot
    db.commit()
    return {"count":len(factors),"factors":factors,"status":"FACTORS_ONLY"}


@router.get("/{piece_id}/pb1/ibge-factors")
def get_pb1_ibge_factors(piece_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    piece = _owned(piece_id, db, user)
    snapshot = piece.snapshot or {}
    record = (snapshot.get("pb1") or {}).get("ibge_factors")
    points = (snapshot.get("topcon") or {}).get("pb1_draft") or []
    if record and record.get("points") == [{"name":p["name"],"latitude":p["latitude"],"longitude":p["longitude"]} for p in points]:
        return {"record":record}
    return {"record":None}


@router.get("/{piece_id}/pb1/report.pdf")
def pb1_report_pdf(piece_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.services.pb1_report import build_pb1_report
    piece = _owned(piece_id, db, user)
    snapshot = piece.snapshot or {}
    assets = ((snapshot.get("pb1") or {}).get("assets") or {})
    paths = {}
    for kind in ("pb1_color", "pb1_dtm"):
        asset = assets.get(kind)
        if asset and exists_matching(user.id, piece.id, asset):
            paths[kind] = stored_file_path(user.id, piece.id, kind, asset["sha256"])
    try:
        data = build_pb1_report(piece.title, str(piece.id), snapshot, paths)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return Response(content=data, media_type="application/pdf", headers={
        "Content-Disposition": 'attachment; filename="RELATORIO_TECNICO_PB1.pdf"',
        "Cache-Control": "private, no-store",
    })


@router.get("/{piece_id}/pb1/technical-preview")
def get_pb1_technical_preview(piece_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    piece = _owned(piece_id, db, user)
    return {"preview": ((piece.snapshot or {}).get("pb1") or {}).get("technical_preview")}


@router.post("/{piece_id}/ps4/files/{kind}")
def upload_ps4_file(
    piece_id: UUID, kind: str, file: UploadFile = File(...),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """Upload privado; nunca recebe nome de arquivo como caminho no disco."""
    piece = _owned(piece_id, db, user)
    if kind not in ("raster", "report"):
        raise HTTPException(422, "Tipo deve ser raster ou report.")
    filename = (file.filename or "").lower()
    if not filename.endswith((".tif", ".tiff") if kind == "raster" else (".pdf",)):
        raise HTTPException(422, "Extensão inválida: envie GeoTIFF ou PDF.")
    try:
        record = store_uploaded_asset(file.file, user.id, piece.id, kind)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    snapshot = dict(piece.snapshot or {})
    ps4 = dict(snapshot.get("ps4") or {})
    assets = dict(ps4.get("assets") or {})
    assets[kind] = record
    ps4["assets"] = assets
    if kind == "raster":
        ps4.pop("checkpoint_analysis", None)
        # Novo arquivo manual cancela vínculo com qualquer recorte ainda em fila.
        ps4.pop("import_job_id", None)
        ps4.pop("source_provenance", None)
    # Substituir um arquivo invalida qualquer aprovação anterior.
    ps4.pop("approval", None)
    ps4.pop("completed_at", None)
    snapshot["ps4"] = ps4
    # Caso ainda não exista formulário, manter a evidência sem forçar campos.
    if "submission" in ps4:
        snapshot["ps4"] = {
            **ps4,
            "validation": evaluate_verified_ps4(
                PS4Submission.model_validate(ps4["submission"]),
                assets, user.id, piece.id,
            ),
        }
    piece.snapshot = snapshot
    piece.status = "DRAFT"
    db.commit()
    db.refresh(piece)
    return {"piece_id": str(piece.id), "asset": record,
            "ps4": piece.snapshot["ps4"]}


class PS4DiagnosticVertex(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)


class PS4RasterDiagnosticInput(BaseModel):
    vertices: list[PS4DiagnosticVertex] = Field(default_factory=list, max_length=500)


class PS4Checkpoint(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    gnss_longitude: float = Field(ge=-180, le=180)
    gnss_latitude: float = Field(ge=-90, le=90)
    image_longitude: float = Field(ge=-180, le=180)
    image_latitude: float = Field(ge=-90, le=90)
    used_for_orthorectification: bool = False


class PS4CheckpointExclusion(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=8, max_length=1000)


class PS4CheckpointAnalysisInput(BaseModel):
    checkpoints: list[PS4Checkpoint] = Field(default_factory=list, max_length=500)
    exclusions: list[PS4CheckpointExclusion] = Field(default_factory=list, max_length=500)


@router.post("/{piece_id}/ps4/checkpoint-analysis")
def ps4_checkpoint_analysis(
    piece_id: UUID, payload: PS4CheckpointAnalysisInput,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """EMQ independente em referência métrica do GeoTIFF, sem certificação automática."""
    from app.services.ps4_planimetric_check import evaluate_checkpoints

    piece = _owned(piece_id, db, user)
    raster = (((piece.snapshot or {}).get("ps4") or {}).get("assets") or {}).get("raster")
    if not isinstance(raster, dict) or not exists_matching(user.id, piece.id, raster):
        raise HTTPException(409, "GeoTIFF privado ausente ou sem integridade.")
    try:
        result = evaluate_checkpoints(
            [point.model_dump() for point in payload.checkpoints],
            raster.get("metadata") or {},
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    snapshot = dict(piece.snapshot or {})
    ps4 = dict(snapshot.get("ps4") or {})
    previous_analysis = ps4.get("checkpoint_analysis") or {}
    same_raster = previous_analysis.get("raster_sha256") == raster["sha256"]
    history = list(previous_analysis.get("exclusion_log") or []) if same_raster else []
    previous_names = {
        str(item.get("name", "")).strip()
        for item in (previous_analysis.get("checkpoints") or [])
        if isinstance(item, dict)
    } if same_raster else set()
    current_names = {item.name for item in payload.checkpoints}
    requested_names = [item.name for item in payload.exclusions]
    if len(requested_names) != len(set(requested_names)):
        raise HTTPException(422, "Exclusões repetidas na mesma avaliação.")
    if any(name not in previous_names or name in current_names for name in requested_names):
        raise HTTPException(
            422, "A exclusão deve referir ponto salvo da avaliação anterior e ausente da nova amostra."
        )
    now = datetime.now(timezone.utc).isoformat()
    history.extend({
        "name": exclusion.name, "reason": exclusion.reason.strip(),
        "excluded_at": now, "user_id": str(user.id),
    } for exclusion in payload.exclusions)
    ps4["checkpoint_analysis"] = {
        "raster_sha256": raster["sha256"],
        "checkpoints": payload.model_dump(mode="json")["checkpoints"],
        "result": result,
        "exclusion_log": history,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }
    snapshot["ps4"] = ps4
    piece.snapshot = snapshot
    db.add(piece)
    db.commit()
    return {"piece_id": str(piece.id), "raster_sha256": raster["sha256"],
            "result": result}


@router.post("/{piece_id}/ps4/raster-diagnostic")
def ps4_raster_diagnostic(
    piece_id: UUID, payload: PS4RasterDiagnosticInput,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """Inspeção privada do GeoTIFF real; não fornece RMS ou aprovação PS4."""
    from app.services.ps4_raster_diagnostic import (
        diagnose_ps4_raster, analyze_raster_visual,
    )

    piece = _owned(piece_id, db, user)
    raster = (((piece.snapshot or {}).get("ps4") or {}).get("assets") or {}).get("raster")
    if not isinstance(raster, dict) or not exists_matching(
        user.id, piece.id, raster
    ):
        raise HTTPException(409, "GeoTIFF da peça ausente ou com falha de integridade.")
    try:
        diagnostic = diagnose_ps4_raster(
            raster.get("metadata") or {},
            [vertex.model_dump() for vertex in payload.vertices],
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        diagnostic["visual_analysis"] = analyze_raster_visual(
            stored_file_path(user.id, piece.id, "raster", raster["sha256"]),
        )
    except (ValueError, RuntimeError) as exc:
        # A inspeção estrutural continua útil quando a amostra radiométrica falha.
        diagnostic["visual_analysis"] = {
            "status": "UNAVAILABLE",
            "reason": str(exc),
            "positional_accuracy_m": None,
            "sigma_e_m": None,
            "sigma_n_m": None,
        }
    return {"piece_id": str(piece.id),
            "raster_sha256": raster["sha256"], "diagnostic": diagnostic}


@router.get("/{piece_id}/ps4/files/{kind}")
def download_ps4_file(
    piece_id: UUID, kind: str,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    piece = _owned(piece_id, db, user)
    asset = ((piece.snapshot or {}).get("ps4") or {}).get("assets", {}).get(kind)
    if not isinstance(asset, dict) or not exists_matching(
        user.id, piece.id, asset
    ):
        raise HTTPException(404, "Arquivo PS4 indisponível ou com falha de integridade.")
    path = stored_file_path(user.id, piece.id, kind, asset["sha256"])
    return FileResponse(
        path,
        media_type="image/tiff" if kind == "raster" else "application/pdf",
        filename="orbital-ps4.tif" if kind == "raster" else "ortorretificacao-ps4.pdf",
        headers={"Cache-Control": "no-store"},
    )


class PS4RTAttestation(BaseModel):
    report_scene_correspondence_checked: bool
    orthorectification_rms_checked: bool
    positional_accuracy_checked: bool
    feature_identification_checked: bool
    source_resolution_checked: bool
    technical_responsibility_accepted: bool
    documentary_metric_traceability_checked: bool = False


@router.post("/{piece_id}/ps4/approve")
def approve_ps4(
    piece_id: UUID, payload: PS4RTAttestation,
    request: Request,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """Registra a revisão humana; não certifica automaticamente o raster."""
    piece = _owned(piece_id, db, user)
    current = ((piece.snapshot or {}).get("ps4") or {})
    if "submission" not in current:
        raise HTTPException(409, "Preencha o formulário PS4 antes da revisão.")
    submitted = PS4Submission.model_validate(current["submission"])
    pending_job = current.get("import_job_id")
    if pending_job:
        try:
            inpe_job = read_job(UUID(str(pending_job)))
        except (OSError, ValueError, KeyError):
            inpe_job = {}
        if inpe_job.get("status") in ACTIVE:
            raise HTTPException(
                409, "O recorte CBERS ainda está em processamento; aprovação suspensa."
            )
    assets = current.get("assets", {})
    validation = evaluate_verified_ps4(submitted, assets, user.id, piece.id)
    if validation["status"] == "BLOCKED":
        raise HTTPException(409, {"message": "PS4 possui pendências.",
                                  "blockers": validation["blockers"]})
    if validation["status"] == "NOT_APPLICABLE":
        raise HTTPException(409, "PS4 não se aplica; utilize a conclusão sem V.")
    topcon = (piece.snapshot or {}).get("topcon") or {}
    draft_vertices = topcon.get("ps4_draft") or []
    if len(draft_vertices) != len(submitted.vertices):
        raise HTTPException(
            409, "Os vértices V da evidência divergem do traçado salvo na peça."
        )
    for expected, actual in zip(draft_vertices, submitted.vertices):
        if (
            expected.get("name") != actual.vertex_id
            or expected.get("longitude") != actual.longitude
            or expected.get("latitude") != actual.latitude
            or expected.get("scene_id") != submitted.evidence.scene_id
        ):
            raise HTTPException(
                409, "O traçado salvo não corresponde aos vértices submetidos à revisão PS4."
            )
    checks = payload.model_dump()
    if submitted.evidence and submitted.evidence.validation_mode == "LEGACY":
        # Compatibilidade com peças anteriores sem documentação estruturada.
        checks["documentary_metric_traceability_checked"] = True
    if not all(checks.values()):
        raise HTTPException(422, "Todos os itens de revisão do RT são obrigatórios.")
    profile = user.professional_profile_json or {}
    crea = str(profile.get("crea") or "").strip()
    art = str(profile.get("art") or "").strip()
    if not crea or not art:
        raise HTTPException(
            422, "Informe CREA e ART no perfil profissional antes de aprovar PS4."
        )
    approval = {
        "status": "APPROVED_BY_RT",
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "user_id": str(user.id),
        "rt_name": user.full_name,
        "crea": crea,
        "art": art,
        "checks": checks,
        "raster_sha256": assets["raster"]["sha256"],
        "report_sha256": assets["report"]["sha256"],
        "validation_mode": submitted.evidence.validation_mode,
        "report_page": submitted.evidence.report_page,
        "accuracy_source": submitted.evidence.accuracy_source,
        "report_metric_reference": submitted.evidence.report_metric_reference,
    }
    snapshot = dict(piece.snapshot or {})
    snapshot["ps4"] = {
        "submission": submitted.model_dump(mode="json"),
        "assets": assets,
        "validation": {**validation, "status": "APPROVED_BY_RT",
                       "requires_rt_review": False,
                       "message": "Revisão técnica registrada pelo RT."},
        "approval": approval,
        **({"source_provenance": current["source_provenance"]}
           if current.get("source_provenance") else {}),
        **({"import_job_id": current["import_job_id"]}
           if current.get("import_job_id") else {}),
    }
    piece.snapshot = snapshot
    db.add(piece)
    write_audit(
        db, action="PS4_RT_APPROVED", user_id=user.id,
        entity_type="technical_piece", entity_id=str(piece.id),
        details={
            "raster_sha256": approval["raster_sha256"],
            "report_sha256": approval["report_sha256"],
            "crea": crea, "art": art,
            "validation_mode": submitted.evidence.validation_mode,
            "report_page": submitted.evidence.report_page,
            "accuracy_source": submitted.evidence.accuracy_source,
            "report_metric_reference": submitted.evidence.report_metric_reference,
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(piece)
    return {"piece_id": str(piece.id), "ps4": piece.snapshot["ps4"]}


@router.post("/{piece_id}/ps4/complete-no-v")
def complete_ps4_not_applicable(
    piece_id: UUID, request: Request,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """Conclui apenas a subetapa PS4 quando não há vértices adicionais."""
    piece = _owned(piece_id, db, user)
    ps4 = ((piece.snapshot or {}).get("ps4") or {})
    try:
        submitted = PS4Submission.model_validate(ps4["submission"])
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, "Informe a opção de necessidade de vértices.") from exc
    if submitted.needs_additional_vertices or submitted.vertices:
        raise HTTPException(409, "Há vértices V registrados; não aplicável é inválido.")
    topcon = (piece.snapshot or {}).get("topcon") or {}
    if topcon.get("ps4_draft") or any(
        p.get("sigef_method") == "PS4"
        for p in (topcon.get("boundary") or [])
    ):
        raise HTTPException(
            409, "A peça possui vértices PS4 persistidos. Remova-os antes de dispensar a etapa."
        )
    snapshot = dict(piece.snapshot or {})
    snapshot["ps4"] = {
        "submission": submitted.model_dump(mode="json"),
        "assets": ps4.get("assets", {}),
        # Não manter vínculo com recorte remoto quando a etapa foi dispensada.
        "validation": {
            "status": "NOT_APPLICABLE", "blockers": [],
            "requires_rt_review": False,
            "message": "Subetapa concluída sem vértices V adicionais.",
        },
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    piece.snapshot = snapshot
    db.add(piece)
    write_audit(
        db, action="PS4_NOT_APPLICABLE", user_id=user.id,
        entity_type="technical_piece", entity_id=str(piece.id),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(piece)
    return {"piece_id": str(piece.id), "ps4": piece.snapshot["ps4"]}


@router.get("/{piece_id}/ps4/raster/tiles/{digest}/{z}/{x}/{y}.png")
def ps4_raster_tile(
    piece_id: UUID, digest: str, z: int, x: int, y: int,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """Tiles privados, versionados pelo hash. Sem fallback para provedores externos."""
    piece = _owned(piece_id, db, user)
    asset = ((piece.snapshot or {}).get("ps4") or {}).get("assets", {}).get("raster")
    if not isinstance(asset, dict) or asset.get("sha256") != digest:
        raise HTTPException(404, "Ortoimagem não vinculada à peça.")
    try:
        mercator_tile_bounds(z, x, y)
        path = stored_file_path(user.id, piece.id, "raster", digest)
        if not path.is_file():
            raise HTTPException(404, "GeoTIFF não encontrado.")
        if not tile_intersects_footprint(asset.get("metadata") or {}, z, x, y):
            return Response(
                transparent_png_tile(), media_type="image/png",
                headers={"Cache-Control": "private, max-age=3600", "X-PS4-Empty-Tile": "true"},
            )
        image = render_png_tile(path, z, x, y)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            503, str(exc), headers={"Retry-After": "2"}
        ) from exc
    return Response(
        image, media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600", "X-PS4-Raster-SHA256": digest},
    )


class PS4InpeCropInput(BaseModel):
    item_id: str = Field(min_length=10, max_length=180)
    collection: str = Field(default="CB4A-WPM-PCA-FUSED-1")
    bbox: tuple[float, float, float, float]


@router.get("/{piece_id}/ps4/inpe/scenes/{item_id}")
def ps4_inpe_scene_info(
    piece_id: UUID, item_id: str, collection: str = "CB4A-WPM-PCA-FUSED-1",
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """Analisa metadados STAC oficiais e explica documentação que falta."""
    _owned(piece_id, db, user)
    try:
        item = fetch_inpe_item(item_id, collection)
        return examine_inpe_item(item)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/{piece_id}/ps4/inpe/prepare", status_code=202)
def ps4_prepare_inpe_scene(
    piece_id: UUID, payload: PS4InpeCropInput,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """Enfileira recorte COG; não executa GDAL no request HTTP."""
    piece = _owned(piece_id, db, user)
    ps4 = dict((piece.snapshot or {}).get("ps4") or {})
    # Evita recortes idênticos da mesma cena, bbox e coleção:
    # o raster já armazenado deve ser reutilizado na interface.
    raster = (ps4.get("assets") or {}).get("raster")
    provenance = ps4.get("source_provenance") or {}
    previous_bbox = provenance.get("crop_bbox_wgs84")
    if (
        isinstance(raster, dict)
        and provenance.get("item_id") == payload.item_id
        and provenance.get("collection") == payload.collection
        and isinstance(previous_bbox, list)
        and len(previous_bbox) == 4
        and all(abs(float(old) - float(new)) < 1e-8
                for old, new in zip(previous_bbox, payload.bbox))
        and exists_matching(user.id, piece.id, raster)
    ):
        raise HTTPException(
            409,
            "Recorte INPE idêntico já armazenado nesta peça. "
            "Utilize a imagem existente em vez de criar outra cópia.",
        )
    previous_id = ps4.get("import_job_id")
    if previous_id:
        try:
            previous = read_job(UUID(str(previous_id)))
        except (OSError, ValueError, KeyError):
            previous = {}
        if previous.get("status") in ACTIVE:
            raise HTTPException(409, "Já existe recorte CBERS em processamento nesta peça.")
    try:
        job = new_job(user.id, piece.id, payload.item_id, payload.collection, payload.bbox)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    snapshot = dict(piece.snapshot or {})
    ps4["import_job_id"] = job["id"]
    # Nunca manter aprovação vigente enquanto uma nova origem está sendo preparada.
    ps4.pop("approval", None)
    ps4.pop("completed_at", None)
    ps4["validation"] = {
        "status": "BLOCKED",
        "blockers": ["Novo recorte CBERS em preparação; aprovação anterior revogada."],
        "requires_rt_review": True,
    }
    snapshot["ps4"] = ps4
    piece.snapshot = snapshot
    db.add(piece)
    db.commit()
    try:
        save_job(job)
    except OSError as exc:
        raise HTTPException(503, "Não foi possível criar trabalho de recorte.") from exc
    return {"piece_id": str(piece.id), "job": safe_status(job),
            "message": "Recorte enfileirado. Acompanhe no painel PS4."}


@router.get("/{piece_id}/ps4/inpe/jobs/{job_id}")
def ps4_inpe_job_status(
    piece_id: UUID, job_id: UUID,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """Status privado, vinculado ao usuário, peça e job ativo."""
    piece = _owned(piece_id, db, user)
    linked = ((piece.snapshot or {}).get("ps4") or {}).get("import_job_id")
    if str(linked) != str(job_id):
        raise HTTPException(404, "Trabalho não vinculado à peça.")
    try:
        job = read_job(job_id)
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(404, "Trabalho não encontrado.") from exc
    if job.get("piece_id") != str(piece.id) or job.get("user_id") != str(user.id):
        raise HTTPException(404, "Trabalho não encontrado.")
    return {"job": safe_status(job)}

@router.get("/{piece_id}/ps4/inpe/metadata.xml")
def ps4_download_official_xml(
    piece_id: UUID,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """Arquivo XML do INPE preservado e verificado; não substitui relatório RMS."""
    piece = _owned(piece_id, db, user)
    provenance = ((piece.snapshot or {}).get("ps4") or {}).get("source_provenance") or {}
    metadata = provenance.get("technical_xml") or {}
    try:
        path = verified_official_xml_path(user.id, piece.id, metadata)
    except (ValueError, AttributeError) as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(
        path, media_type="application/xml",
        filename=f"INPE_{provenance.get('item_id', 'CBERS')}_METADADOS.xml",
        headers={"Cache-Control": "private, no-store"},
    )


# PS1: ciclo independente de arquivos e consolidação.
@router.post("/{piece_id}/ps1/files/{kind}")
def upload_ps1_file(
    piece_id: UUID, kind: str, file: UploadFile = File(...),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    piece = _owned(piece_id, db, user)
    if kind not in ("ps1_ortho", "ps1_dtm", "ps1_report"):
        raise HTTPException(422, "Tipo de arquivo PS1 inválido.")
    suffixes = (".pdf",) if kind == "ps1_report" else (".tif", ".tiff")
    if not (file.filename or "").lower().endswith(suffixes):
        raise HTTPException(422, "Formato de arquivo PS1 inválido.")
    try:
        asset = store_uploaded_asset(file.file, user.id, piece.id, kind)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    snapshot = dict(piece.snapshot or {})
    assets = dict((snapshot.get("ps1") or {}).get("assets") or {})
    assets[kind] = asset
    snapshot["ps1"] = {"assets": assets}
    piece.snapshot = snapshot
    db.commit()
    return {"asset": asset}


@router.get("/{piece_id}/ps1/assets")
def get_ps1_assets(piece_id: UUID, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    piece = _owned(piece_id, db, user)
    return {"assets": ((piece.snapshot or {}).get("ps1") or {}).get("assets", {})}


class PS1FinalizeInput(BaseModel):
    start: str
    vertices: list[dict] = Field(min_length=1, max_length=4997)
    checkpoints: list[dict] = Field(min_length=1, max_length=5000)
    category: str
    vertical_kind: str
    vertical_reference: str = Field(min_length=5, max_length=500)
    report_reference: str = Field(min_length=5, max_length=500)
    ibge_output: str = Field(default="", max_length=1000000)
    rt_reviewed: bool = False
    gsd_m: float = Field(gt=0, allow_inf_nan=False)
    pec_reference: str = Field(min_length=5, max_length=500)
    gsd_compatible: bool = False
    pec_compatible: bool = False
    independent_sample_representative: bool = False
    report_matches_assets_and_residuals: bool = False
    datum_and_vertical_accuracy_checked: bool = False
    sirgas2000_and_boundaries_checked: bool = False


@router.post("/{piece_id}/ps1/finalize")
def finalize_ps1(piece_id: UUID, payload: PS1FinalizeInput, request: Request,
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Calcula e persiste o resultado técnico, sem representar certificação SIGEF."""
    from app.services.ps1_consolidation import consolidate_ps1
    from app.services.pb1_dtm_sampling import sample_pb1_dtm
    from shapely.geometry import Point, shape
    piece = _owned(piece_id, db, user)
    snapshot = dict(piece.snapshot or {})
    assets = (snapshot.get("ps1") or {}).get("assets", {})
    profile = user.professional_profile_json or {}
    if not payload.rt_reviewed or not profile.get("crea") or not profile.get("art"):
        raise HTTPException(422, "Confirme revisão técnica e informe CREA e ART.")
    if not all((payload.gsd_compatible, payload.pec_compatible,
                payload.independent_sample_representative,
                payload.report_matches_assets_and_residuals,
                payload.datum_and_vertical_accuracy_checked,
                payload.sirgas2000_and_boundaries_checked)):
        raise HTTPException(422, "Revisão PS1 incompleta: GSD, PEC, amostra, relatório, datum e limites.")
    for kind in ("ps1_ortho", "ps1_dtm", "ps1_report"):
        if not exists_matching(user.id, piece.id, assets.get(kind) or {}):
            raise HTTPException(422, "Arquivo PS1 ausente ou alterado: " + kind)
    try:
        footprint = shape(assets["ps1_ortho"]["metadata"]["wgs84_extent"])
        for vertex in payload.vertices:
            if not footprint.covers(Point(vertex["longitude"], vertex["latitude"])):
                raise ValueError("Vértice fora do ortomosaico PS1.")
        dtm = assets["ps1_dtm"]
        path = stored_file_path(user.id, piece.id, "ps1_dtm", dtm["sha256"])
        nodata = dtm["metadata"]["bands"][0].get("no_data_value")
        topcon = dict(snapshot.get("topcon") or {})
        source_boundary = topcon.get("boundary") or []
        initial = next((p for p in source_boundary if p.get("sigef_vertex_code") == payload.start), {})
        boundary_type = str(initial.get("boundary_type") or "")
        if (boundary_type.startswith("LA") and payload.category != "ARTIFICIAL") or (
            boundary_type.startswith("LN") and payload.category not in ("NATURAL", "ARTIFICIAL")
        ):
            raise ValueError("Categoria incompatível com o código de limite; use o critério mais restritivo.")
        if not boundary_type.startswith(("LA", "LN")) or not initial.get("confrontant"):
            raise ValueError("Confirme limite e confrontante do trecho antes de concluir.")
        vertices = [dict(v) for v in payload.vertices]
        if payload.vertical_kind == "NORMAL":
            from app.services.pb1_ibge import parse_ibge_output
            points = [{"name": v["code"], "longitude": v["longitude"], "latitude": v["latitude"]} for v in vertices]
            factors = parse_ibge_output(payload.ibge_output, points)
            for vertex in vertices:
                vertex["factor"], vertex["factor_sigma"] = factors[vertex["code"]]
        result = consolidate_ps1(source_boundary, payload.start,
                    vertices, payload.checkpoints, payload.category,
                    payload.vertical_kind, lambda lon, lat: sample_pb1_dtm(path, lon, lat, nodata))
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    # Aprovação humana explícita, não certificação automática de PEC.
    for v in result["generated"]:
        v["height_reference_confirmed"] = True
        v["sigma_reference_confirmed"] = True
        v["derived_calculation"].update(status="APPROVED_BY_RT", accuracy_verified=True)
    approval = {"status": "APPROVED_BY_RT", "user_id": str(user.id),
                "approved_at": datetime.now(timezone.utc).isoformat(),
                "crea": str(profile["crea"]), "art": str(profile["art"]),
                "hashes": {k: assets[k]["sha256"] for k in ("ps1_ortho", "ps1_dtm", "ps1_report")}}
    snapshot["ps1"] = {"assets": assets, "calculation": result,
                      "submission": payload.model_dump(), "approval": approval}
    piece.snapshot = snapshot
    write_audit(db, action="PS1_RT_APPROVED", user_id=user.id,
                entity_type="technical_piece", entity_id=str(piece.id),
                details={"count": len(result["generated"]), "art": str(profile["art"])},
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"))
    db.commit()
    return result


@router.get("/{piece_id}/ps1/raster/tiles/{digest}/{z}/{x}/{y}.png")
def ps1_raster_tile(piece_id: UUID, digest: str, z: int, x: int, y: int,
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    piece = _owned(piece_id, db, user)
    asset = (((piece.snapshot or {}).get("ps1") or {}).get("assets") or {}).get("ps1_ortho")
    if not isinstance(asset, dict) or asset.get("sha256") != digest:
        raise HTTPException(404, "Ortomosaico PS1 não vinculado à peça.")
    try:
        mercator_tile_bounds(z, x, y)
        path = stored_file_path(user.id, piece.id, "ps1_ortho", digest)
        if not path.is_file():
            raise HTTPException(404, "Ortomosaico não encontrado.")
        png = (render_png_tile(path, z, x, y, mode="pb1_color")
               if tile_intersects_footprint(asset.get("metadata") or {}, z, x, y)
               else transparent_png_tile())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


class PB1ApproveInput(BaseModel):
    vertices: list[dict] = Field(min_length=3, max_length=5000)
    category: str
    inaccessible_reason: str = Field(default="", max_length=2000)
    position_reference: str = Field(min_length=12, max_length=2000)
    rt_reviewed: bool = False


@router.post("/{piece_id}/pb1/approve")
def approve_pb1(piece_id: UUID, payload: PB1ApproveInput, request: Request,
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Registra revisão humana de dados documentados calculados no servidor."""
    from app.services.pb1_approval import validate_pb1_vertices, validate_pb1_perimeter
    piece = _owned(piece_id, db, user)
    snapshot = dict(piece.snapshot or {})
    top = snapshot.get("topcon") or {}
    pb = dict(snapshot.get("pb1") or {})
    assets = pb.get("assets") or {}
    profile = user.professional_profile_json or {}
    if not payload.rt_reviewed or not all(str(profile.get(k) or "").strip() for k in ("crea","art","incra_code")):
        raise HTTPException(422,"Confirme a revisão RT e informe CREA, ART e código INCRA no perfil.")
    source = top.get("pb1_source") or {}
    if not all(str(source.get(k) or "").strip() for k in ("product","accuracy_reference","vertical_reference")):
        raise HTTPException(422,"Documente produto, exatidão posicional e referencial vertical da base.")
    if not payload.position_reference.strip() or not (top.get("pb1_closure") or {}).get("confirmed"):
        raise HTTPException(422,"Confirme a fonte de posicionamento e o fechamento PB1.")
    hashes = {k:v["sha256"] for k,v in assets.items() if k in ("pb1_dtm","pb1_color")}
    if "pb1_dtm" not in hashes or not all(exists_matching(user.id,piece.id,assets[k]) for k in hashes):
        raise HTTPException(422,"MDT ou outro raster vinculado ausente/alterado.")
    preview = pb.get("partial_preview") or {}
    if preview.get("dtm_sha256") != hashes["pb1_dtm"] or preview.get("color_sha256") != hashes.get("pb1_color"):
        raise HTTPException(422,"Recalcule o PB1 com os dados e rasters atuais.")
    try:
        validate_pb1_perimeter(payload.vertices,top)
        generated = validate_pb1_vertices(payload.vertices,top.get("pb1_draft") or [],preview,
            str(profile["incra_code"]).strip().upper(),payload.category,payload.inaccessible_reason)
    except (ValueError,TypeError,KeyError) as exc:
        raise HTTPException(422,str(exc)) from exc
    decision = {"status":"APPROVED_BY_RT","vertices":payload.vertices,"generated":generated,
        "hashes":hashes,"category":payload.category,"position_reference":payload.position_reference,
        "inaccessible_reason":payload.inaccessible_reason,"user_id":str(user.id),
        "crea":str(profile["crea"]),"art":str(profile["art"]),
        "approved_at":datetime.now(timezone.utc).isoformat()}
    pb["approval"]=decision
    pb["review_status"]="APPROVED_BY_RT"
    snapshot["pb1"]=pb
    piece.snapshot=snapshot
    write_audit(db, action="PB1_RT_APPROVED", user_id=user.id,
        entity_type="technical_piece",entity_id=str(piece.id),
        details={"count":len(generated),"art":str(profile["art"]),"category":payload.category},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"))
    db.commit()
    return {"status":"APPROVED_BY_RT","count":len(generated)}
