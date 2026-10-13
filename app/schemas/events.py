"""Domain specific event models and query parameters."""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field
from app.schemas.geojson import PointGeometry


class BoundingBoxQuery(BaseModel):
    """Bounding box filter: min_lon, min_lat, max_lon, max_lat (EPSG:4326)."""
    min_lon: float = Field(..., ge=-180, le=180)
    min_lat: float = Field(..., ge=-90, le=90)
    max_lon: float = Field(..., ge=-180, le=180)
    max_lat: float = Field(..., ge=-90, le=90)


class EventQueryParams(BaseModel):
    category: Optional[str] = Field(None, description="Filter by category")
    subcategory: Optional[str] = Field(None, description="Filter by subcategory")
    district: Optional[str] = Field(None, description="Filter by Rotterdam district")
    min_severity: Optional[int] = Field(None, ge=1, le=5)
    active_only: bool = Field(True, description="Only return unexpired events")
    limit: int = Field(100, ge=1, le=1000, description="Max items to return")
    offset: int = Field(0, ge=0)


class HealthStatus(BaseModel):
    status: str
    timestamp: datetime
    service: str
    details: Optional[dict] = None


# ---------------------------------------------------------------------------
# Rotterdam Events Domain Schemas (/api/v1/events)
# ---------------------------------------------------------------------------

class EventPrice(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None
    currency: str = "EUR"


class EventVenueInfo(BaseModel):
    name: str
    address: Optional[str] = None
    postal_code: Optional[str] = None
    city: str = "Rotterdam"
    district: Optional[str] = None
    coordinates: Optional[List[float]] = None  # GeoJSON standard [longitude, latitude]
    latitude: Optional[float] = None  # Explicit GPS latitude (WGS84)
    longitude: Optional[float] = None  # Explicit GPS longitude (WGS84)


class RotterdamEventProperties(BaseModel):
    id: str = Field(..., description="Unique event identifier (e.g. tm_123, fixture_456)")
    title: str = Field(..., description="Event title or match headline")
    description: Optional[str] = Field(None, description="Short description or lineup")
    category: Literal["event"] = "event"
    subcategory: str = Field(
        ...,
        description="Subcategory: concert, stadium_fixture, festival, theatre, comedy, sports, cultural, exhibition",
    )
    source: str = Field(
        ...,
        description="Source provider: ticketmaster, stadium_fixtures, municipal_festivals, open_agenda",
    )
    venue: EventVenueInfo
    start_time: datetime = Field(..., description="Start date and time (ISO 8601 UTC)")
    end_time: Optional[datetime] = Field(None, description="Estimated end date and time")
    district: str = Field(..., description="Official validated Rotterdam district")
    price: Optional[EventPrice] = None
    ticket_url: Optional[str] = Field(None, description="Direct URL to ticket purchase or reservation")
    image_url: Optional[str] = Field(None, description="Hero or promotional image URL")
    status: str = Field("scheduled", description="Event status: scheduled, rescheduled, cancelled, postponed")
    details: Dict[str, Any] = Field(default_factory=dict, description="Domain specific attributes")


class RotterdamEventFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: PointGeometry
    properties: RotterdamEventProperties


class RotterdamEventFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: List[RotterdamEventFeature] = Field(default_factory=list)
    total_count: Optional[int] = Field(None, description="Total matching events")


class VenueSummary(BaseModel):
    name: str
    address: Optional[str] = None
    district: Optional[str] = None
    coordinates: List[float] = Field(..., description="[longitude, latitude]")
    total_events: int = 0
    subcategories: List[str] = Field(default_factory=list)


class VenueListResponse(BaseModel):
    total_venues: int
    venues: List[VenueSummary]


class EventStatsResponse(BaseModel):
    total_events: int
    subcategories: Dict[str, int]
    sources: Dict[str, int]
    districts: Dict[str, int]
    top_venues: Dict[str, int]
    timestamp: datetime
