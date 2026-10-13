"""Strict RFC 7946 GeoJSON models and RotterdamLive Canonical schemas."""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


class PointGeometry(BaseModel):
    type: Literal["Point"] = "Point"
    # GeoJSON specifies [longitude, latitude]
    coordinates: List[float] = Field(
        ...,
        min_length=2,
        max_length=3,
        description="Coordinates in [longitude, latitude] or [lon, lat, elevation] format",
    )


class PolygonGeometry(BaseModel):
    type: Literal["Polygon"] = "Polygon"
    coordinates: List[List[List[float]]] = Field(
        ...,
        description="Linear rings defining polygon coordinates [[ [lon, lat], ... ]]",
    )


class LineStringGeometry(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: List[List[float]] = Field(
        ...,
        min_length=2,
        description="Coordinates for LineString [[lon, lat], ...]",
    )


class MultiPolygonGeometry(BaseModel):
    type: Literal["MultiPolygon"] = "MultiPolygon"
    coordinates: List[List[List[List[float]]]] = Field(
        ...,
        description="Coordinates for MultiPolygon",
    )


GeometryType = Union[PointGeometry, LineStringGeometry, PolygonGeometry, MultiPolygonGeometry]



class CanonicalEventProperties(BaseModel):
    id: str = Field(..., description="Unique event identifier")
    category: Literal[
        "emergency", "mobility", "news", "environment", "spatial", "amenity", "utility", "event", "crowd"
    ] = Field(..., description="High-level category")
    subcategory: str = Field(
        ..., description="Specific subcategory (e.g. brandweer, parking, bridge, transit, weather)"
    )
    severity: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Standardized severity level from 1 (info/routine) to 5 (critical)",
    )
    timestamp: datetime = Field(
        ..., description="Timestamp when event occurred or was reported"
    )
    expires_at: Optional[datetime] = Field(
        None, description="Expiration timestamp for transient live events"
    )
    district: Optional[str] = Field(
        None, description="Rotterdam neighborhood / district name (e.g. Centrum, Delfshaven)"
    )
    title: str = Field(..., description="Human-readable title or headline")
    details: Dict[str, Any] = Field(
        default_factory=dict, description="Domain-specific structured attributes"
    )


class GeoJSONFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: GeometryType
    properties: CanonicalEventProperties


class GeoJSONFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: List[GeoJSONFeature] = Field(default_factory=list)
    total_count: Optional[int] = Field(
        None, description="Optional total count when paginated"
    )
