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
from app.services.ps4_assets import store_uploaded_asset, stored_file_path, exists_matching
from app.services.technical_import import parse_sigef_ods
from app.services.topcon_import import parse_topcon_report, MAX_BYTES
from app.services.topcon_perimeter_review import review_topcon_perimeter
from app.services.sigef_parcel_review import review_sigef_parcels
from app.services.sigef_ods_reviewed import build_reviewed_sigef_ods
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
    user: User = Depends(get_current_user),
):
    """Exporta ODS para conferência técnica, não certificação oficial."""
    try:
        data = build_reviewed_sigef_ods(payload.model_dump())
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
    previous = (piece.snapshot or {}).get("ps4", {}) if piece else {}
    if "ps4" not in snapshot and previous:
        # Salvamentos de memorial/layout não invalidam o RT quando o traçado
        # e os dados topográficos permanecem exatamente iguais.
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
        if same_geometry and previous.get("approval"):
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
            snapshot["ps4"] = {"assets": previous.get("assets", {})}
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
    snapshot["ps4"] = {
        "submission": submitted.model_dump(mode="json"),
        "assets": assets,
        "validation": validation,
    }
    return snapshot


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
        "validation": current.get("validation", {
            "status": "BLOCKED",
            "blockers": ["Validação PS4 não iniciada."],
            "requires_rt_review": True,
        }),
    }


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
    if not filename.endswith(".tif" if kind == "raster" else ".pdf"):
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
    assets = current.get("assets", {})
    validation = evaluate_verified_ps4(submitted, assets, user.id, piece.id)
    if validation["status"] == "BLOCKED":
        raise HTTPException(409, {"message": "PS4 possui pendências.",
                                  "blockers": validation["blockers"]})
    if validation["status"] == "NOT_APPLICABLE":
        raise HTTPException(409, "PS4 não se aplica; utilize a conclusão sem V.")
    checks = payload.model_dump()
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
    }
    snapshot = dict(piece.snapshot or {})
    snapshot["ps4"] = {
        "submission": submitted.model_dump(mode="json"),
        "assets": assets,
        "validation": {**validation, "status": "APPROVED_BY_RT",
                       "requires_rt_review": False,
                       "message": "Revisão técnica registrada pelo RT."},
        "approval": approval,
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
    snapshot = dict(piece.snapshot or {})
    snapshot["ps4"] = {
        "submission": submitted.model_dump(mode="json"),
        "assets": ps4.get("assets", {}),
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
