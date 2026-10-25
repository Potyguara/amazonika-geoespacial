from __future__ import annotations

from datetime import datetime
from uuid import UUID

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Table, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


# Vinculação territorial exigida pelos endpoints de usuários e autorização.
# A tabela pode já existir na VPS; create_all só a cria quando estiver ausente.
authorized_area_users = Table(
    "authorized_area_users",
    Base.metadata,
    Column("area_id", UUID(as_uuid=True), ForeignKey("authorized_areas.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)



class AuthorizedArea(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "authorized_areas"

    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        index=True,
    )

    geom = mapped_column(
        Geometry(
            geometry_type="MULTIPOLYGON",
            srid=4674,
            spatial_index=True,
        ),
        nullable=False,
    )


class AuditLog(Base, UUIDMixin):
    __tablename__ = "audit_logs"

    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )
