"""Domain specific event models and query parameters."""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


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
