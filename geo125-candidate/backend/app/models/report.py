from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class ReportEmission(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "report_emissions"

    analysis_id: Mapped[UUID] = mapped_column(
        ForeignKey("analyses.id"),
        nullable=False,
        index=True,
    )

    issued_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    tracking_code: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        unique=True,
        index=True,
    )

    public_token: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        index=True,
    )

    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="GENERATING",
    )

    pdf_path: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    map_path: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    pdf_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    analysis_name: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
    )

    analysis_snapshot: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    __table_args__ = (
        Index(
            "ix_report_emissions_analysis_issued",
            "analysis_id",
            "issued_at",
        ),
    )
