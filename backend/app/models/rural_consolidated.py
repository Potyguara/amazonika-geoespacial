"""Persisted, isolated FULL FARM consolidated report job.

Separate from pre-existing territorial report emissions. The initial renderer
only uses immutable snapshots of a completed territorial analysis. Other
sections remain NOT_RUN, never misreported as negative findings.
"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, Integer, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, UUIDMixin


class RuralConsolidatedJob(Base, UUIDMixin):
    __tablename__ = "rural_consolidated_jobs"

    source_analysis_id: Mapped[UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="QUEUED")
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    report_type: Mapped[str] = mapped_column(String(40), nullable=False, default="FULL_FARM_CONSOLIDATED")
    snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    pdf_sha256: Mapped[str | None] = mapped_column(String(64))
    pdf_relative_path: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
