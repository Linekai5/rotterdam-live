"""SQLAlchemy 2.0 Declarative Models with PostGIS Geometries and Spatial Indexing."""
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    Integer,
    String,
    Index,
    UniqueConstraint,
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


class DistrictDemographics(Base):
    """Official CBS Demographics & Household Structure per Rotterdam District."""
    __tablename__ = "district_demographics"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # e.g. "cbs_WK059901"
    district_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    district_name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    total_population: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    population_density_km2: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    men: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    women: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    age_0_14: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    age_15_24: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    age_25_44: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    age_45_64: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    age_65_plus: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_households: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    single_person_households: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    single_person_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    average_household_size: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    average_income_per_inhabitant: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="CBS", nullable=False)
    data_year: Mapped[int] = mapped_column(Integer, default=2026, nullable=False)
    details: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_district_demographics_code", "district_code"),
        Index("idx_district_demographics_name", "district_name"),
    )


class DistrictHousingMetrics(Base):
    """Housing Volume, Dwelling Sizes, Construction Eras & Livability per District."""
    __tablename__ = "district_housing_metrics"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # e.g. "housing_WK059901"
    district_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    district_name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    total_residential_units: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_surface_area_m2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    median_surface_area_m2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min_surface_area_m2: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_surface_area_m2: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pre_war_count: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)
    pre_war_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    post_war_count: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)
    post_war_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    late_20th_count: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)
    late_20th_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    modern_count: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)
    modern_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    average_woz_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    owner_occupied_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    social_rent_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    private_rent_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    livability_index: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    safety_index: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    physical_index: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    social_index: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    amenity_counts: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_district_housing_code", "district_code"),
        Index("idx_district_housing_name", "district_name"),
    )


class RotterdamEvent(Base):
    """
    Verified Cultural, Entertainment, Stadium Fixture, and Municipal Festival Event in Rotterdam.
    Ingested asynchronously from Ticketmaster, Stadium Fixture iCal feeds (De Kuip, Het Kasteel, Woudestein),
    and Municipal Festival Agendas.
    """
    __tablename__ = "rotterdam_events"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    category: Mapped[str] = mapped_column(String(64), default="event", index=True, nullable=False)
    subcategory: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # concert, stadium_fixture, festival, theatre, comedy, sports, cultural, exhibition
    source: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # ticketmaster, stadium_fixtures, municipal_festivals, open_agenda
    venue_name: Mapped[str] = mapped_column(String(256), index=True, nullable=False)
    venue_address: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    venue_postal_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    district: Mapped[str] = mapped_column(String(128), index=True, nullable=False)  # Assigned via PostGIS ST_Within

    # PostGIS geometry: exact Point in EPSG:4326
    geom = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False,
    )

    price_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_currency: Mapped[Optional[str]] = mapped_column(String(8), default="EUR", nullable=True)
    ticket_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="scheduled", nullable=False)
    details: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
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
        Index("idx_events_start_time", "start_time"),
        Index("idx_events_subcat_active", "subcategory", "is_active"),
        Index("idx_events_district_active", "district", "is_active"),
        Index("idx_events_source", "source"),
        Index("idx_events_venue", "venue_name"),
    )


class CrowdTelemetryHistory(Base):
    """
    Historical crowdness telemetry snapshots and residual projections per Rotterdam district.
    Truncated to 15-minute intervals. Zero in-request computation invariant.
    """
    __tablename__ = "crowd_telemetry_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    district: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    crowd_index: Mapped[float] = mapped_column(Float, nullable=False)
    crowd_status: Mapped[str] = mapped_column(String(64), nullable=False)
    parking_occupancy_avg_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    active_events_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    precipitation_mm_h: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    temperature_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    details: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("district", "timestamp", name="uq_crowd_hist_district_time"),
        Index("idx_crowd_hist_district_time", "district", text("timestamp DESC")),
    )


class CityTrafficSegment(Base):
    """
    Monitored motorway and urban arterial traffic corridor in Rotterdam.
    Stores real-time speed, travel times, delays, and congestion tiers with LineString geometry.
    """
    __tablename__ = "city_traffic_segments"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    road_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)  # motorway, urban_arterial
    free_flow_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    current_travel_time_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    delay_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    speed_kmh: Mapped[float] = mapped_column(Float, nullable=False)
    congestion_level: Mapped[str] = mapped_column(String(32), index=True, nullable=False)  # free_flow, moderate, heavy, standstill
    district: Mapped[Optional[str]] = mapped_column(String(128), index=True, nullable=True)

    geom = mapped_column(
        Geometry(geometry_type="LINESTRING", srid=4326, spatial_index=True),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_traffic_segments_congestion", "congestion_level"),
        Index("idx_traffic_segments_road_type", "road_type"),
    )




