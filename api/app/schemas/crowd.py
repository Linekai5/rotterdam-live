"""Pydantic schemas for the Rotterdam Live Crowdness & Real-Time Forecaster Domain.

Strict RFC 7946 GeoJSON compliance, sub-5ms Redis caching models, and multi-horizon autoregressive forecasts.
"""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.geojson import MultiPolygonGeometry, PolygonGeometry, PointGeometry


class CrowdMetricsDetails(BaseModel):
    """Raw mathematical metrics and contextual factors for crowdness index derivation."""
    base_score: float = Field(..., description="Diurnal baseline B_d(dow, hour) in [0, 75]")
    event_surge: float = Field(..., description="Event surge contribution in [0, 50]")
    weather_shift: float = Field(..., description="Weather shift contribution in [-15, +15]")
    live_residual: float = Field(..., description="Live residual Delta_d(t0) = C_live - C_base_hat")
    structural_baseline: float = Field(..., description="Structural baseline C_base_hat = B_d + EventSurge + WeatherShift")
    parking_occupancy_avg_pct: Optional[float] = Field(None, description="Average parking garage occupancy percentage if monitored")
    monitored_garages_count: int = Field(0, description="Number of monitored garages in district")
    active_events_count: int = Field(0, description="Active or upcoming events within district or 1.5km buffer")
    emergency_count: int = Field(0, description="Active P2000 emergency incidents in district")
    roadworks_count: int = Field(0, description="Active municipal roadworks in district")
    precipitation_mm_h: float = Field(0.0, description="Rainfall intensity in mm/hour")
    temperature_c: Optional[float] = Field(None, description="Current temperature in Celsius")
    wind_bft: Optional[int] = Field(None, description="Wind speed in Beaufort")
    weather_condition: Optional[str] = Field(None, description="Weather description / summary")

    model_config = ConfigDict(populate_by_name=True)


class CrowdForecastPoint(BaseModel):
    """Hourly autoregressive forecast projection point at horizon h hours."""
    horizon_hours: float = Field(..., description="Horizon offset in hours (h >= 0)")
    target_time: datetime = Field(..., description="Projected target timestamp (t0 + h)")
    crowd_index: float = Field(..., ge=0.0, le=100.0, description="Projected normalized crowdness index in [0, 100]")
    crowd_status: str = Field(..., description="English classification (Quiet, Moderate, Busy, Saturated)")
    crowd_status_nl: str = Field(..., description="Dutch classification (Rustig, Normaal, Druk, Zeer druk)")
    base_score: float = Field(..., description="Diurnal baseline at horizon")
    event_surge: float = Field(..., description="Event surge at horizon")
    weather_shift: float = Field(..., description="Weather shift at horizon")
    residual_contribution: float = Field(..., description="Decayed residual Delta * exp(-0.5 * h)")

    model_config = ConfigDict(populate_by_name=True)


class DistrictCrowdProperties(BaseModel):
    """District properties for the RFC 7946 Crowdness GeoJSON Feature."""
    district_code: str = Field(..., description="Official CBS district code (e.g. 'WK059901')")
    district_name: str = Field(..., description="Rotterdam district name (e.g. 'Rotterdam Centrum')")
    crowd_index: float = Field(..., ge=0.0, le=100.0, description="Normalized crowdness index in [0, 100]")
    crowd_status: str = Field(..., description="Status category: Quiet, Moderate, Busy, Saturated")
    crowd_status_nl: str = Field(..., description="Dutch label: Rustig, Normaal, Druk, Zeer druk")
    has_monitored_garages: bool = Field(..., description="True if district has live parking telemetry")
    parking_occupancy_avg_pct: Optional[float] = Field(None, description="Average parking occupancy percentage")
    active_events_count: int = Field(0, description="Active events within 1.5km buffer")
    precipitation_mm_h: float = Field(0.0, description="Rainfall intensity in mm/h")
    temperature_c: Optional[float] = Field(None, description="Air temperature in Celsius")
    details: CrowdMetricsDetails = Field(..., description="Raw metrics breakdown")
    timestamp: datetime = Field(..., description="Observation timestamp (truncated 15m)")
    updated_at: datetime = Field(..., description="Snapshot generation timestamp")

    model_config = ConfigDict(populate_by_name=True)


class DistrictCrowdFeature(BaseModel):
    """RFC 7946 GeoJSON Feature representing a district's crowdness state."""
    type: Literal["Feature"] = "Feature"
    id: str = Field(..., description="District code identifier")
    geometry: Union[MultiPolygonGeometry, PolygonGeometry, PointGeometry] = Field(..., description="PostGIS boundary")
    properties: DistrictCrowdProperties = Field(..., description="Telemetry properties")

    model_config = ConfigDict(populate_by_name=True)


class CrowdLiveFeatureCollection(BaseModel):
    """Master Crowdness GeoJSON FeatureCollection across all 19 Rotterdam municipal districts."""
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: List[DistrictCrowdFeature] = Field(default_factory=list, description="District polygon features")
    total_districts: int = Field(..., description="Total districts evaluated (19)")
    timestamp: datetime = Field(..., description="Evaluation timestamp")
    city_average_crowd_index: float = Field(..., description="Municipal average crowd index")
    busiest_district: Optional[str] = Field(None, description="District with highest crowd index")
    quietest_district: Optional[str] = Field(None, description="District with lowest crowd index")

    model_config = ConfigDict(populate_by_name=True)


class DistrictCrowdDetailResponse(BaseModel):
    """Comprehensive district crowd passport including live observation and 24h horizon forecast."""
    district_code: str = Field(..., description="District code")
    district_name: str = Field(..., description="District name")
    crowd_index: float = Field(..., ge=0.0, le=100.0, description="Current crowdness index")
    crowd_status: str = Field(..., description="Quiet, Moderate, Busy, Saturated")
    crowd_status_nl: str = Field(..., description="Rustig, Normaal, Druk, Zeer druk")
    has_monitored_garages: bool = Field(..., description="Whether district has parking sensors")
    parking_occupancy_avg_pct: Optional[float] = Field(None, description="Garages occupancy %")
    active_events_count: int = Field(0, description="Active events count")
    precipitation_mm_h: float = Field(0.0, description="Precipitation rate mm/h")
    temperature_c: Optional[float] = Field(None, description="Temperature C")
    details: CrowdMetricsDetails = Field(..., description="Metrics breakdown")
    timestamp: datetime = Field(..., description="Current timestamp")
    forecast: List[CrowdForecastPoint] = Field(default_factory=list, description="24-hour autoregressive projection series")

    model_config = ConfigDict(populate_by_name=True)


class DistrictForecastMatrixItem(BaseModel):
    """Forecast projection for a single district over multiple horizons."""
    district_code: str = Field(..., description="District code")
    district_name: str = Field(..., description="District name")
    current_index: float = Field(..., description="Live crowd index at t0")
    current_status: str = Field(..., description="Current status")
    current_status_nl: str = Field(..., description="Current status NL")
    horizons: List[CrowdForecastPoint] = Field(default_factory=list, description="Forecast timeline")

    model_config = ConfigDict(populate_by_name=True)


class CrowdForecastMatrixResponse(BaseModel):
    """Multi-horizon forecast matrix across all Rotterdam municipal districts."""
    timestamp: datetime = Field(..., description="Base observation timestamp t0")
    horizons_evaluated_hours: List[float] = Field(default_factory=list, description="Evaluated horizon offsets")
    districts: List[DistrictForecastMatrixItem] = Field(default_factory=list, description="Districts forecast matrix")

    model_config = ConfigDict(populate_by_name=True)


class CrowdHistoryItem(BaseModel):
    """Historical telemetry record from crowd_telemetry_history."""
    id: int = Field(..., description="Record primary key")
    district: str = Field(..., description="District name")
    timestamp: datetime = Field(..., description="15-minute slot timestamp")
    crowd_index: float = Field(..., description="Recorded crowd index")
    crowd_status: str = Field(..., description="Recorded status")
    parking_occupancy_avg_pct: Optional[float] = Field(None, description="Average parking occupancy")
    active_events_count: int = Field(0, description="Active events count")
    precipitation_mm_h: float = Field(0.0, description="Precipitation in mm/h")
    temperature_c: Optional[float] = Field(None, description="Temperature")
    details: Dict[str, Any] = Field(default_factory=dict, description="Raw metrics breakdown")

    model_config = ConfigDict(populate_by_name=True)


class CrowdHistoryResponse(BaseModel):
    """Historical crowd telemetry query response."""
    district: Optional[str] = Field(None, description="Filtered district name if specified")
    total_records: int = Field(..., description="Number of historical records returned")
    history: List[CrowdHistoryItem] = Field(default_factory=list, description="Chronological telemetry records")

    model_config = ConfigDict(populate_by_name=True)


class CrowdOverviewStats(BaseModel):
    """Municipal-level crowd statistics and telemetry status overview."""
    timestamp: datetime = Field(..., description="Current evaluation timestamp")
    city_average_crowd_index: float = Field(..., description="Average crowd index across all 19 districts")
    quiet_districts_count: int = Field(..., description="Districts with index 0-25")
    moderate_districts_count: int = Field(..., description="Districts with index 26-50")
    busy_districts_count: int = Field(..., description="Districts with index 51-75")
    peak_districts_count: int = Field(..., description="Districts with index 76-100")
    busiest_district: Optional[str] = Field(None, description="Highest crowdness district")
    busiest_district_index: Optional[float] = Field(None, description="Highest score")
    quietest_district: Optional[str] = Field(None, description="Lowest crowdness district")
    quietest_district_index: Optional[float] = Field(None, description="Lowest score")
    monitored_garages_total: int = Field(..., description="Total monitored garages evaluated")
    citywide_parking_occupancy_pct: Optional[float] = Field(None, description="Total citywide parking occupancy")
    active_events_total: int = Field(..., description="Total active cultural & stadium events")

    model_config = ConfigDict(populate_by_name=True)
