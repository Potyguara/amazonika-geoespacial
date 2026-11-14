"""Rascunhos das peças técnicas, isolados pelo usuário autenticado."""
from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.auth import User
from app.models.technical_piece import TechnicalPiece
from app.services.auth import get_current_user, require_permission
from app.services.technical_import import parse_sigef_ods
from app.services.topcon_import import parse_topcon_report, MAX_BYTES
from app.services.topcon_perimeter_review import review_topcon_perimeter
from app.services.sigef_parcel_review import review_sigef_parcels
from app.services.sigef_ods_reviewed import build_reviewed_sigef_ods
from app.services.vertical_datum import convert_altitudes

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


@router.post("", status_code=201)
def create_piece(
    payload: PieceInput,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    piece = TechnicalPiece(user_id=user.id, title=payload.title, snapshot=payload.snapshot)
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
    piece.snapshot = payload.snapshot
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
