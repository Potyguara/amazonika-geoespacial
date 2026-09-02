from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import get_db
from app.models.auth import Role, User
from app.models.security import AuthorizedArea
from app.schemas.users import (
    AuthorizedAreaAssignment,
    UserCreate,
    UserUpdate,
)
from app.services.audit import write_audit
from app.services.auth import require_permission


router = APIRouter(
    prefix="/users",
    tags=["Usuários"],
    dependencies=[Depends(require_permission("users.manage"))],
)


ALLOWED_ROLES = {"ADMINISTRADOR", "ANALISTA"}


def _user_payload(db: Session, user: User) -> dict:
    area_ids = list(
        db.scalars(
            text(
                """
                SELECT area_id
                FROM authorized_area_users
                WHERE user_id = :user_id
                ORDER BY area_id
                """
            ),
            {"user_id": user.id},
        )
    )

    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "is_active": user.is_active,
        "roles": sorted(role.code for role in user.roles),
        "authorized_area_ids": [str(area_id) for area_id in area_ids],
    }


def _get_role(db: Session, code: str) -> Role:
    normalized = code.strip().upper()

    if normalized not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=422,
            detail="Perfil inválido. Use ADMINISTRADOR ou ANALISTA.",
        )

    role = db.scalar(
        select(Role).where(Role.code == normalized)
    )

    if not role:
        raise HTTPException(
            status_code=500,
            detail=f"Perfil {normalized} não cadastrado.",
        )

    return role


def _ensure_not_last_admin(
    db: Session,
    user: User,
    *,
    new_role: str | None = None,
    new_active: bool | None = None,
) -> None:
    current_roles = {role.code for role in user.roles}

    if "ADMINISTRADOR" not in current_roles:
        return

    will_remain_admin = (
        (new_role is None or new_role == "ADMINISTRADOR")
        and (new_active is None or new_active is True)
    )

    if will_remain_admin:
        return

    active_admins = db.scalar(
        select(func.count(func.distinct(User.id)))
        .select_from(User)
        .join(User.roles)
        .where(
            Role.code == "ADMINISTRADOR",
            User.is_active.is_(True),
        )
    )

    if (active_admins or 0) <= 1:
        raise HTTPException(
            status_code=409,
            detail="Não é possível remover ou desativar o último administrador ativo.",
        )


@router.get("")
def list_users(db: Session = Depends(get_db)):
    users = list(
        db.scalars(
            select(User)
            .order_by(User.is_active.desc(), User.full_name, User.email)
        )
    )

    return [_user_payload(db, user) for user in users]


@router.get("/{user_id}")
def get_user(
    user_id: UUID,
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)

    if not user:
        raise HTTPException(404, "Usuário não encontrado.")

    return _user_payload(db, user)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users.manage")),
):
    email = payload.email.strip().lower()

    existing = db.scalar(
        select(User).where(User.email == email)
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Já existe um usuário com este e-mail.",
        )

    role = _get_role(db, payload.role)

    user = User(
        email=email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        is_active=payload.is_active,
        roles=[role],
    )

    db.add(user)
    db.flush()

    write_audit(
        db,
        action="USER_CREATED",
        user_id=current_user.id,
        entity_type="user",
        entity_id=str(user.id),
        details={
            "email": user.email,
            "role": role.code,
            "is_active": user.is_active,
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(user)

    return _user_payload(db, user)


@router.patch("/{user_id}")
def update_user(
    user_id: UUID,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users.manage")),
):
    user = db.get(User, user_id)

    if not user:
        raise HTTPException(404, "Usuário não encontrado.")

    role = None

    if payload.role is not None:
        role = _get_role(db, payload.role)

    _ensure_not_last_admin(
        db,
        user,
        new_role=role.code if role else None,
        new_active=payload.is_active,
    )

    if payload.email is not None:
        email = payload.email.strip().lower()

        duplicate = db.scalar(
            select(User).where(
                User.email == email,
                User.id != user.id,
            )
        )

        if duplicate:
            raise HTTPException(
                409,
                "Já existe um usuário com este e-mail.",
            )

        user.email = email

    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()

    if payload.password is not None:
        user.password_hash = hash_password(payload.password)

    if payload.is_active is not None:
        user.is_active = payload.is_active

    if role is not None:
        user.roles = [role]

        if role.code == "ADMINISTRADOR":
            db.execute(
                text(
                    """
                    DELETE FROM authorized_area_users
                    WHERE user_id = :user_id
                    """
                ),
                {"user_id": user.id},
            )

    write_audit(
        db,
        action="USER_UPDATED",
        user_id=current_user.id,
        entity_type="user",
        entity_id=str(user.id),
        details={
            "email": user.email,
            "roles": [r.code for r in user.roles],
            "is_active": user.is_active,
            "password_changed": payload.password is not None,
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(user)

    return _user_payload(db, user)


@router.put("/{user_id}/authorized-areas")
def set_authorized_areas(
    user_id: UUID,
    payload: AuthorizedAreaAssignment,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users.manage")),
):
    user = db.get(User, user_id)

    if not user:
        raise HTTPException(404, "Usuário não encontrado.")

    roles = {role.code for role in user.roles}

    if "ANALISTA" not in roles:
        raise HTTPException(
            422,
            "Somente usuários ANALISTA podem possuir restrições territoriais.",
        )

    requested_ids = list(dict.fromkeys(payload.area_ids))

    if requested_ids:
        existing_ids = set(
            db.scalars(
                select(AuthorizedArea.id).where(
                    AuthorizedArea.id.in_(requested_ids)
                )
            )
        )

        missing = set(requested_ids) - existing_ids

        if missing:
            raise HTTPException(
                422,
                "Uma ou mais áreas autorizadas não existem.",
            )

    db.execute(
        text(
            """
            DELETE FROM authorized_area_users
            WHERE user_id = :user_id
            """
        ),
        {"user_id": user.id},
    )

    for area_id in requested_ids:
        db.execute(
            text(
                """
                INSERT INTO authorized_area_users (
                    area_id,
                    user_id
                )
                VALUES (
                    :area_id,
                    :user_id
                )
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "area_id": area_id,
                "user_id": user.id,
            },
        )

    write_audit(
        db,
        action="USER_AREAS_UPDATED",
        user_id=current_user.id,
        entity_type="user",
        entity_id=str(user.id),
        details={
            "area_ids": [str(area_id) for area_id in requested_ids],
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()

    return _user_payload(db, user)
