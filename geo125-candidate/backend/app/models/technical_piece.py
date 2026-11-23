from __future__ import annotations

from uuid import UUID
from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin, TimestampMixin


class TechnicalPiece(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "technical_pieces"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
