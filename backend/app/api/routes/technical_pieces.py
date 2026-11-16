"""Rascunhos das peças técnicas, isolados pelo usuário autenticado."""
from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.auth import User
from app.models.technical_piece import TechnicalPiece
from app.services.auth import get_current_user, require_permission
from app.services.technical_import import parse_sigef_ods
from app.services.ps4_validation import PS4Submission, evaluate_ps4

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


@router.put("/{piece_id}/ps4")
def save_ps4(
    piece_id: UUID, payload: PS4Submission,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """Salva PS4 de forma transacional, sem sobrescrever o restante do snapshot."""
    piece = _owned(piece_id, db, user)
    validation = evaluate_ps4(payload)
    snapshot = dict(piece.snapshot or {})
    snapshot["ps4"] = {
        "submission": payload.model_dump(mode="json"),
        "validation": validation,
    }
    piece.snapshot = snapshot
    # Nenhum resultado preliminar autoriza concluir a peça automaticamente.
    if piece.status != "DRAFT":
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
    return (piece.snapshot or {}).get("ps4", {
        "submission": {"needs_additional_vertices": True, "vertices": []},
        "validation": {"status": "BLOCKED", "blockers": [
            "Validação PS4 não iniciada."
        ], "requires_rt_review": True},
    })
