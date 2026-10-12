"""SQLAlchemy 2.0 Declarative Models with PostGIS Geometries and Spatial Indexing."""
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import (
    DateTime,
    Integer,
    String,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from geoalchemy2 import Geometry


class Base(DeclarativeBase):
    pass


class LiveEvent(Base):
    """Canonical spatial live event table."""
    __tablename__ = "live_events"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    category: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    subcategory: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    severity: Mapped[int] = mapped_column(Integer, default=1, index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )
    district: Mapped[Optional[str]] = mapped_column(
        String(128), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    details: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    
    # PostGIS geometry: supports Point or Polygon, EPSG:4326
    geom = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=True),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_live_events_category_time", "category", "timestamp"),
        Index("idx_live_events_active", "expires_at", "category"),
    )


class RotterdamDistrict(Base):
    """Official Gemeente Rotterdam Wijk- en Buurtgrenzen (Spatial Baseline)."""
    __tablename__ = "rotterdam_districts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    district_type: Mapped[str] = mapped_column(String(32), default="wijk", nullable=False)
    properties: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )

    # PostGIS MultiPolygon in EPSG:4326
    geom = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=True),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
