from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.security import (
    generate_session_token,
    hash_session_token,
    session_expiration,
    verify_password,
)
from app.db.session import get_db
from app.models.auth import User, UserSession
from app.schemas.auth import CurrentUserRead, LoginRequest, LoginResponse
from app.schemas.security import LocationVerificationRequest
from app.services.audit import write_audit
from app.services.auth import (
    SESSION_COOKIE_NAME,
    get_current_session,
    get_current_user,
    user_payload,
)


router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    email = payload.email.strip().lower()

    user = db.scalar(
        select(User).where(User.email == email)
    )

    if (
        not user
        or not user.is_active
        or not verify_password(user.password_hash, payload.password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha inválidos.",
        )

    token = generate_session_token()

    session = UserSession(
        user_id=user.id,
        token_hash=hash_session_token(token),
        expires_at=session_expiration(12),
    )

    user.last_login_at = datetime.now(timezone.utc)

    db.add(session)
    db.flush()

    write_audit(
        db,
        action="LOGIN_SUCCESS",
        user_id=user.id,
        entity_type="session",
        entity_id=str(session.id),
        details={"email": user.email},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(user)

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=12 * 60 * 60,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )

    return {"user": user_payload(user)}


@router.get("/me", response_model=CurrentUserRead)
def me(user: User = Depends(get_current_user)):
    return user_payload(user)


class ProfessionalProfileUpdate(BaseModel):
    full_name: str = Field(min_length=3, max_length=255)
    rg: str | None = Field(default=None, max_length=50)
    cpf: str | None = Field(default=None, max_length=18)
    profession: str | None = Field(default=None, max_length=150)
    specialization: str | None = Field(default=None, max_length=255)
    crea: str | None = Field(default=None, max_length=100)
    visto: str | None = Field(default=None, max_length=100)
    incra_code: str | None = Field(default=None, max_length=80)
    art: str | None = Field(default=None, max_length=120)


@router.get("/me/professional-profile")
def get_professional_profile(user: User = Depends(get_current_user)):
    return {"full_name": user.full_name, **(user.professional_profile_json or {})}


@router.put("/me/professional-profile")
def update_professional_profile(
    payload: ProfessionalProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    info = payload.model_dump(exclude={"full_name"})
    cpf = (info.get("cpf") or "").strip()
    if cpf and (len("".join(char for char in cpf if char.isdigit())) != 11):
        raise HTTPException(422, "CPF deve conter 11 dígitos.")
    user.full_name = payload.full_name.strip()
    user.professional_profile_json = {
        key: value.strip() if isinstance(value, str) else value
        for key, value in info.items()
    }
    db.add(user)
    db.commit()
    return {"full_name": user.full_name, **user.professional_profile_json}


@router.post("/location")
def verify_location(
    payload: LocationVerificationRequest,
    request: Request,
    db: Session = Depends(get_db),
    session: UserSession = Depends(get_current_session),
):
    user = session.user
    roles = {role.code for role in user.roles}

    # Administradores não possuem limitação territorial.
    if "ADMINISTRADOR" in roles:
        return {
            "allowed": True,
            "area_name": None,
            "expires_at": None,
            "message": "Administrador sem restrição territorial.",
        }

    if "ANALISTA" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Perfil sem autorização para validação territorial.",
        )

    # Precisão muito baixa não é adequada para liberar a área de trabalho.
    if (
        payload.accuracy_meters is not None
        and payload.accuracy_meters > 1000
    ):
        write_audit(
            db,
            action="LOCATION_DENIED",
            user_id=user.id,
            entity_type="session",
            entity_id=str(session.id),
            details={
                "reason": "LOW_ACCURACY",
                "latitude": payload.latitude,
                "longitude": payload.longitude,
                "accuracy_meters": payload.accuracy_meters,
            },
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "LOCATION_ACCURACY_TOO_LOW",
                "message": (
                    "A precisão da localização é insuficiente. "
                    "Atualize o GPS e tente novamente."
                ),
            },
        )

    row = db.execute(
        text(
            """
            SELECT
              a.id::text AS id,
              a.name
            FROM authorized_areas a
            INNER JOIN authorized_area_users au
              ON au.area_id = a.id
            WHERE au.user_id = :user_id
              AND a.is_active IS TRUE
              AND ST_Covers(
                a.geom,
                ST_SetSRID(
                  ST_MakePoint(:longitude, :latitude),
                  4674
                )
              )
            ORDER BY a.name
            LIMIT 1
            """
        ),
        {
            "user_id": user.id,
            "latitude": payload.latitude,
            "longitude": payload.longitude,
        },
    ).mappings().first()

    now = datetime.now(timezone.utc)

    if not row:
        session.location_verified_at = now
        session.location_expires_at = None
        session.location_latitude = payload.latitude
        session.location_longitude = payload.longitude
        session.location_accuracy_meters = payload.accuracy_meters

        write_audit(
            db,
            action="LOCATION_DENIED",
            user_id=user.id,
            entity_type="session",
            entity_id=str(session.id),
            details={
                "latitude": payload.latitude,
                "longitude": payload.longitude,
                "accuracy_meters": payload.accuracy_meters,
                "reason": "OUTSIDE_AUTHORIZED_AREA",
            },
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        db.commit()

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "OUTSIDE_AUTHORIZED_AREA",
                "message": (
                    "Sua localização está fora das áreas autorizadas "
                    "para utilização do sistema."
                ),
            },
        )

    expires_at = now + timedelta(minutes=15)

    session.location_verified_at = now
    session.location_expires_at = expires_at
    session.location_latitude = payload.latitude
    session.location_longitude = payload.longitude
    session.location_accuracy_meters = payload.accuracy_meters

    write_audit(
        db,
        action="LOCATION_ALLOWED",
        user_id=user.id,
        entity_type="authorized_area",
        entity_id=row["id"],
        details={
            "area_name": row["name"],
            "latitude": payload.latitude,
            "longitude": payload.longitude,
            "accuracy_meters": payload.accuracy_meters,
            "expires_at": expires_at.isoformat(),
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()

    return {
        "allowed": True,
        "area_name": row["name"],
        "expires_at": expires_at.isoformat(),
        "message": "Localização autorizada.",
    }


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    token = request.cookies.get(SESSION_COOKIE_NAME)

    if token:
        token_hash = hash_session_token(token)
        session = db.scalar(
            select(UserSession).where(
                UserSession.token_hash == token_hash,
                UserSession.revoked_at.is_(None),
            )
        )

        if session:
            session.revoked_at = datetime.now(timezone.utc)

            write_audit(
                db,
                action="LOGOUT",
                user_id=session.user_id,
                entity_type="session",
                entity_id=str(session.id),
                details={},
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )

            db.commit()

    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
