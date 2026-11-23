from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2 import Geometry

from app.db.base import Base, UUIDMixin


class StateBoundary(Base, UUIDMixin):
    __tablename__ = "state_boundaries"

    uf: Mapped[str] = mapped_column(
        String(2),
        unique=True,
        index=True,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    ibge_code: Mapped[str] = mapped_column(
        String(2),
        unique=True,
        index=True,
        nullable=False,
    )

    geom: Mapped[object] = mapped_column(
        Geometry(
            geometry_type="MULTIPOLYGON",
            srid=4674,
            spatial_index=True,
        ),
        nullable=False,
    )
