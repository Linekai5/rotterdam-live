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


class CityAmenity(Base):
    """Municipal civic amenities and urban infrastructure (data.rotterdam.nl)."""
    __tablename__ = "city_amenities"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    category: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="amenity")
    subcategory: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # toilet, water_tap, ev_charger, camera, aed
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    district: Mapped[Optional[str]] = mapped_column(String(128), index=True, nullable=True)
    details: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    # PostGIS geometry: supports Point or Polygon, EPSG:4326
    geom = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=True),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(default=True, index=True, nullable=False)
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
        Index("idx_city_amenities_subcat_active", "subcategory", "is_active"),
        Index("idx_city_amenities_district_subcat", "district", "subcategory"),
    )


class RotterdamAddress(Base):
    """Official Kadaster BAG Addresses (Gemeentecode 0599 Rotterdam)."""
    __tablename__ = "rotterdam_addresses"

    address_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # BAG Verblijfsobject ID (e.g. 0599010000...)
    pand_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)  # Linked BAG Pand ID
    street_name: Mapped[str] = mapped_column(String(256), nullable=False)
    house_number: Mapped[int] = mapped_column(Integer, nullable=False)
    house_letter: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    house_addition: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(16), index=True, nullable=True)
    city: Mapped[str] = mapped_column(String(128), default="Rotterdam", nullable=False)
    purpose: Mapped[Optional[str]] = mapped_column(String(256), index=True, nullable=True)  # winkelfunctie, woonfunctie, etc.
    surface_area: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    construction_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    district: Mapped[Optional[str]] = mapped_column(String(128), index=True, nullable=True)

    # PostGIS geometry: exact doorway Point in EPSG:4326
    geom = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
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
        Index("idx_addresses_postcode_num", "postal_code", "house_number"),
        Index("idx_addresses_district", "district"),
        Index("idx_addresses_purpose", "purpose"),
    )


class RotterdamRetail(Base):
    """Physical Commercial Shop, Supermarket, and Retail Facility across Rotterdam."""
    __tablename__ = "rotterdam_retail"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), index=True, nullable=False)
    brand: Mapped[Optional[str]] = mapped_column(String(256), index=True, nullable=True)
    shop_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # supermarket, clothes, bakery, etc.
    street_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    house_number: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(16), index=True, nullable=True)
    city: Mapped[str] = mapped_column(String(128), default="Rotterdam", nullable=False)
    district: Mapped[Optional[str]] = mapped_column(String(128), index=True, nullable=True)
    bag_address_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    bag_pand_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    opening_hours: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    wheelchair: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    details: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    # PostGIS geometry: exact Point in EPSG:4326
    geom = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(default=True, index=True, nullable=False)
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
        Index("idx_retail_shop_district", "shop_type", "district"),
        Index("idx_retail_brand", "brand"),
    )

