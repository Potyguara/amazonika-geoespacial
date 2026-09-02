from uuid import UUID
from geoalchemy2 import Geometry
from sqlalchemy import Float, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin, UUIDMixin

class Analysis(Base, UUIDMixin, TimestampMixin):
    __tablename__="analyses"
    name: Mapped[str]=mapped_column(String(180))
    geometry_kind: Mapped[str]=mapped_column(String(20))
    input_geom: Mapped[object]=mapped_column(Geometry(geometry_type="GEOMETRY", srid=4674, spatial_index=False))
    area_hectares: Mapped[float|None]=mapped_column(Float)
    status: Mapped[str]=mapped_column(String(30), default="COMPLETED")
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    warnings_json: Mapped[list]=mapped_column(JSON, default=list)
    source_status_json: Mapped[list]=mapped_column(JSON, default=list)
    error_message: Mapped[str|None]=mapped_column(Text)
    __table_args__=(Index("ix_analyses_input_geom", "input_geom", postgresql_using="gist"),)

class AnalysisResult(Base, UUIDMixin, TimestampMixin):
    __tablename__="analysis_results"
    analysis_id: Mapped[UUID]=mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[UUID]=mapped_column(ForeignKey("sources.id"), index=True)
    source_version_id: Mapped[UUID]=mapped_column(ForeignKey("source_versions.id"), index=True)
    intersects: Mapped[bool]
    matched_features: Mapped[int]=mapped_column(default=0)
    overlap_hectares: Mapped[float]=mapped_column(default=0)
    overlap_percent: Mapped[float]=mapped_column(default=0)
    nearest_distance_meters: Mapped[float|None]
    details: Mapped[dict]=mapped_column(JSON, default=dict)
