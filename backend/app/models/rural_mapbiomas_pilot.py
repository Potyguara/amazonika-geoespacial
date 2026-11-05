"""Audit record for the restricted, billable MapBiomas cartographic pilot.

A committed reservation is recorded BEFORE external requests. Failed attempts
remain as audit records, so automatic retries cannot run up costs.
"""
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin


class RuralMapBiomasPilotRun(Base, UUIDMixin):
    __tablename__ = "rural_mapbiomas_pilot_runs"
    __table_args__ = (
        UniqueConstraint("user_id", "quota_day", name="uq_rural_pilot_user_day"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    quota_day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    subject_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="RESERVED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(60), nullable=True)
    pdf_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
