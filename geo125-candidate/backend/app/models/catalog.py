import enum
from datetime import date, datetime
from uuid import UUID
from geoalchemy2 import Geometry
from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin, UUIDMixin

class SourceKind(str, enum.Enum):
    WFS="WFS"; ARCGIS_FEATURE="ARCGIS_FEATURE"; DOWNLOAD="DOWNLOAD"; GPKG="GPKG"; MANUAL="MANUAL"

class Source(Base, UUIDMixin, TimestampMixin):
    __tablename__="sources"
    slug: Mapped[str]=mapped_column(String(100), unique=True, index=True)
    name: Mapped[str]=mapped_column(String(180))
    institution: Mapped[str]=mapped_column(String(120))
    kind: Mapped[SourceKind]=mapped_column(Enum(SourceKind, name="source_kind"))
    service_url: Mapped[str|None]=mapped_column(Text)
    layer_name: Mapped[str|None]=mapped_column(String(250))
    is_official: Mapped[bool]=mapped_column(Boolean, default=True)
    is_active: Mapped[bool]=mapped_column(Boolean, default=True)
    update_frequency: Mapped[str|None]=mapped_column(String(50))
    metadata_json: Mapped[dict]=mapped_column(JSON, default=dict)
    versions: Mapped[list["SourceVersion"]]=relationship(back_populates="source", cascade="all, delete-orphan")

class SourceVersion(Base, UUIDMixin, TimestampMixin):
    __tablename__="source_versions"
    source_id: Mapped[UUID]=mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    reference_date: Mapped[date|None]=mapped_column(Date)
    imported_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    feature_count: Mapped[int]=mapped_column(Integer, default=0)
    checksum: Mapped[str|None]=mapped_column(String(64))
    original_filename: Mapped[str|None]=mapped_column(String(255))
    status: Mapped[str]=mapped_column(String(30), default="PROCESSING")
    is_current: Mapped[bool]=mapped_column(Boolean, default=False, index=True)
    error_message: Mapped[str|None]=mapped_column(Text)
    source: Mapped[Source]=relationship(back_populates="versions")
    features: Mapped[list["GeoFeature"]]=relationship(back_populates="version", cascade="all, delete-orphan")

class GeoFeature(Base, UUIDMixin):
    __tablename__="geo_features"
    version_id: Mapped[UUID]=mapped_column(ForeignKey("source_versions.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str|None]=mapped_column(String(255), index=True)
    name: Mapped[str|None]=mapped_column(String(500))
    properties: Mapped[dict]=mapped_column(JSON, default=dict)
    geom: Mapped[object]=mapped_column(Geometry(geometry_type="GEOMETRY", srid=4674, spatial_index=False))
    version: Mapped[SourceVersion]=relationship(back_populates="features")
    __table_args__=(Index("ix_geo_features_geom", "geom", postgresql_using="gist"), UniqueConstraint("version_id","external_id",name="uq_feature_version_external"))
