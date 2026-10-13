"""Strict RFC 7946 GeoJSON schemas for the /api/v1/mobility/traffic Subsystem."""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.geojson import LineStringGeometry


class TrafficSegmentProperties(BaseModel):
    """Real-time traffic telemetry and corridor performance indicators."""
    id: str = Field(..., description="Unique corridor identifier, e.g. corridor-a16-southbound")
    name: str = Field(..., description="Human-readable corridor name, e.g. 'A16 Van Brienenoordbrug (Zuidwaarts)'")
    road_type: Literal["motorway", "urban_arterial"] = Field(..., description="Road classification")
    free_flow_seconds: int = Field(..., description="Traversable duration at free-flow speed in seconds")
    current_travel_time_seconds: int = Field(..., description="Current traversal duration in seconds")
    delay_seconds: int = Field(..., description="Current travel delay in seconds (max(0, travel_time - free_flow))")
    speed_kmh: float = Field(..., description="Average vehicle speed in km/h")
    congestion_level: Literal["free_flow", "moderate", "heavy", "standstill"] = Field(
        ..., description="Congestion severity tier"
    )
    district: Optional[str] = Field(None, description="Linked Rotterdam municipal district")
    updated_at: datetime = Field(..., description="Last telemetry update timestamp")

    model_config = ConfigDict(populate_by_name=True)


class TrafficSegmentFeature(BaseModel):
    """RFC 7946 GeoJSON Feature representing a traffic corridor segment."""
    type: Literal["Feature"] = "Feature"
    id: str = Field(..., description="Corridor segment identifier")
    geometry: LineStringGeometry = Field(..., description="WGS84 LineString geometry")
    properties: TrafficSegmentProperties = Field(..., description="Segment performance metrics")

    model_config = ConfigDict(populate_by_name=True)


class TrafficFeatureCollection(BaseModel):
    """RFC 7946 GeoJSON FeatureCollection of monitored Rotterdam traffic corridors."""
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: List[TrafficSegmentFeature] = Field(default_factory=list, description="List of traffic corridor features")
    total_segments: int = Field(..., description="Total number of monitored corridors returned")
    timestamp: datetime = Field(..., description="Evaluation timestamp")

    model_config = ConfigDict(populate_by_name=True)


class TrafficOverviewStats(BaseModel):
    """High-level municipal traffic telemetry overview."""
    timestamp: datetime = Field(..., description="Overview generation timestamp")
    total_segments: int = Field(..., description="Total monitored corridors")
    free_flow_count: int = Field(..., description="Corridors operating at free-flow")
    moderate_count: int = Field(..., description="Corridors experiencing moderate traffic")
    heavy_count: int = Field(..., description="Corridors experiencing heavy traffic")
    standstill_count: int = Field(..., description="Corridors at a standstill")
    average_speed_kmh: float = Field(..., description="Average speed across all monitored corridors")
    average_motorway_speed_kmh: float = Field(..., description="Average speed on the Rotterdam Ring motorways")
    average_arterial_speed_kmh: float = Field(..., description="Average speed on urban arterials")
    total_delay_minutes: float = Field(..., description="Sum of all corridor delays in minutes")
    most_congested_corridor: Optional[str] = Field(None, description="Corridor experiencing worst speed degradation")
    highest_delay_corridor: Optional[str] = Field(None, description="Corridor experiencing largest absolute delay")

    model_config = ConfigDict(populate_by_name=True)
