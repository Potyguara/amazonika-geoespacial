from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_session_token
from app.db.session import get_db
from app.models.auth import User, UserSession


SESSION_COOKIE_NAME = "amazonika_session"


def user_payload(user: User) -> dict:
    role_codes = sorted({role.code for role in user.roles})
    permission_codes = sorted({
        permission.code
        for role in user.roles
        for permission in role.permissions
    })

    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "roles": role_codes,
        "permissions": permission_codes,
    }


def get_current_session(
    session_token: str | None = Cookie(
        default=None,
        alias=SESSION_COOKIE_NAME,
    ),
    db: Session = Depends(get_db),
) -> UserSession:
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação necessária.",
        )

    token_hash = hash_session_token(session_token)

    session = db.scalar(
        select(UserSession)
        .where(
            UserSession.token_hash == token_hash,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > datetime.now(timezone.utc),
        )
    )

    if not session or not session.user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão inválida ou expirada.",
        )

    return session


def get_current_user(
    session: UserSession = Depends(get_current_session),
) -> User:
    return session.user


def require_permission(permission_code: str):
    def dependency(
        session: UserSession = Depends(get_current_session),
    ) -> User:
        user = session.user

        roles = {role.code for role in user.roles}

        granted = {
            permission.code
            for role in user.roles
            for permission in role.permissions
        }

        if permission_code not in granted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permissão insuficiente.",
            )

        # ADMINISTRADOR não depende de validação territorial.
        if "ADMINISTRADOR" in roles:
            return user

        # O ANALISTA só acessa recursos operacionais com localização
        # previamente validada e ainda dentro da janela de autorização.
        if "ANALISTA" in roles:
            now = datetime.now(timezone.utc)

            if (
                session.location_expires_at is None
                or session.location_expires_at <= now
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "LOCATION_REQUIRED",
                        "message": (
                            "Validação de localização necessária para "
                            "acessar o sistema."
                        ),
                    },
                )

        return user

    return dependency
