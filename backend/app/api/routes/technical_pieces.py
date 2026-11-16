"""Rascunhos das peças técnicas, isolados pelo usuário autenticado."""
from __future__ import annotations

from uuid import UUID
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.auth import User
from app.models.technical_piece import TechnicalPiece
from app.services.auth import get_current_user, require_permission
from app.services.technical_import import parse_sigef_ods
from app.services.ps4_validation import PS4Submission, evaluate_verified_ps4
from app.services.ps4_assets import store_uploaded_asset, stored_file_path, exists_matching

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


def _validated_snapshot(
    incoming: dict, piece: TechnicalPiece | None, user: User
) -> dict:
    """Preserva anexos confiáveis e recalcula os resultados a cada gravação."""
    snapshot = dict(incoming)
    previous = (piece.snapshot or {}).get("ps4", {}) if piece else {}
    if "ps4" not in snapshot and previous:
        snapshot["ps4"] = previous
    if "ps4" not in snapshot:
        return snapshot
    requested = snapshot["ps4"]
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
    return (piece.snapshot or {}).get("ps4", {
        "submission": {"needs_additional_vertices": True, "vertices": []},
        "validation": {"status": "BLOCKED", "blockers": [
            "Validação PS4 não iniciada."
        ], "requires_rt_review": True},
    })


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
