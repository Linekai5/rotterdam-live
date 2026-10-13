"""Pydantic schemas for Weather, Precipitation Nowcast, Station Telemetry & Radar Tiles."""
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class RainTimelineItem(BaseModel):
    """Minute-by-minute rain nowcast item."""
    time: str = Field(..., description="Timestamp in HH:MM format")
    intensity_mm_h: float = Field(..., description="Precipitation rate in mm/hour")
    raw_value: int = Field(..., description="Raw Buienradar string value (000-255)")


class RainForecastResponse(BaseModel):
    """Hyper-local 2-hour rain nowcast response."""
    location: Dict[str, float] = Field(..., description="Target coordinates {'lat': float, 'lon': float}")
    generated_at: str = Field(..., description="Generation timestamp in ISO 8601 UTC")
    will_rain_in_2h: bool = Field(..., description="True if rain is expected within the next 2 hours")
    max_intensity_mm_h: float = Field(..., description="Peak precipitation intensity expected in next 2 hours")
    first_rain_in_minutes: Optional[int] = Field(None, description="Minutes until first rain, or null if dry")
    summary: str = Field(..., description="Human-readable rain summary in Dutch")
    timeline: List[RainTimelineItem] = Field(..., description="Chronological 5-minute nowcast timeline")


class WeatherStationProperties(BaseModel):
    """Properties for official KNMI observation stations."""
    station_id: int = Field(..., description="Official KNMI station ID (e.g. 6344, 6330, 6343)")
    station_name: str = Field(..., description="Station name (e.g. Meetstation Rotterdam)")
    regio: Optional[str] = Field(None, description="Region")
    district: Optional[str] = Field(None, description="Resolved Rotterdam municipal district")
    is_primary: bool = Field(False, description="True for primary airport station 6344")
    timestamp: Optional[str] = Field(None, description="Observation ISO timestamp")
    temperature: Optional[float] = Field(None, description="Air temperature in °C")
    feeltemperature: Optional[float] = Field(None, description="Apparent / wind chill temperature in °C")
    groundtemperature: Optional[float] = Field(None, description="Ground temperature in °C")
    humidity: Optional[float] = Field(None, description="Relative humidity percentage")
    airpressure: Optional[float] = Field(None, description="Barometric air pressure in hPa")
    windspeed_ms: Optional[float] = Field(None, description="Wind speed in meters per second")
    windspeed_kmh: Optional[float] = Field(None, description="Wind speed in km/h")
    windspeed_bft: Optional[int] = Field(None, description="Wind speed in Beaufort")
    windgusts_ms: Optional[float] = Field(None, description="Wind gusts in meters per second")
    windgusts_kmh: Optional[float] = Field(None, description="Wind gusts in km/h")
    winddirection: Optional[str] = Field(None, description="Wind direction compass string (e.g. ZZO, WNW)")
    winddirectiondegrees: Optional[int] = Field(None, description="Wind direction in degrees (0-360)")
    precipitation_mm_h: Optional[float] = Field(None, description="Current precipitation intensity in mm/h")
    rainfall_last_hour: Optional[float] = Field(None, description="Accumulated rainfall last hour in mm")
    rainfall_last_24h: Optional[float] = Field(None, description="Accumulated rainfall last 24 hours in mm")
    visibility_m: Optional[float] = Field(None, description="Horizontal visibility in meters")
    sunpower: Optional[float] = Field(None, description="Solar irradiance in W/m²")
    weather_description: Optional[str] = Field(None, description="Weather condition description (Dutch)")
    icon_url: Optional[str] = Field(None, description="30x30 icon image URL")
    full_icon_url: Optional[str] = Field(None, description="96x96 high-resolution icon URL")


class WeatherStationFeature(BaseModel):
    """RFC 7946 GeoJSON Feature for a weather observation station."""
    type: Literal["Feature"] = "Feature"
    id: str = Field(..., description="Feature identifier (e.g. weather-station-6344)")
    geometry: Dict[str, Any] = Field(..., description="GeoJSON Point geometry")
    properties: WeatherStationProperties


class WeatherStationsFeatureCollection(BaseModel):
    """RFC 7946 GeoJSON FeatureCollection of Rotterdam weather stations."""
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: List[WeatherStationFeature]
    total_stations: int = Field(..., description="Total stations in collection")


class RadarFrame(BaseModel):
    """Single radar frame in the RainViewer timeline."""
    time: int = Field(..., description="Unix timestamp of radar capture")
    formatted_time: str = Field(..., description="ISO 8601 UTC formatted timestamp")
    path: str = Field(..., description="Relative radar tile path (e.g. /v2/radar/e7ba36c5dc71)")
    tile_url: str = Field(..., description="Direct MapLibre Slippy tile URL template")


class WeatherRadarResponse(BaseModel):
    """Animated radar tile stream metadata for MapLibre GL raster layers."""
    host: str = Field(..., description="Tile host base URL")
    generated: int = Field(..., description="RainViewer generation unix timestamp")
    tile_size: int = Field(512, description="Tile dimension in pixels")
    tile_url_template: str = Field(..., description="Generic tile URL template with {path}, {z}, {x}, {y}")
    color_scheme: int = Field(2, description="Universal color scheme ID (2 = Rainbow / standard)")
    smooth: int = Field(1, description="Smoothing flag (1 = smoothed)")
    snow: int = Field(1, description="Snow display flag (1 = enabled)")
    past_frames: List[RadarFrame] = Field(..., description="Chronological past radar frames")
    nowcast_frames: List[RadarFrame] = Field(..., description="Forecasted nowcast radar frames")
    latest_frame: Optional[RadarFrame] = Field(None, description="Most recent radar frame")


class LiveWeatherOverview(BaseModel):
    """Instant unified overview of Rotterdam live weather."""
    generated_at: str = Field(..., description="ISO 8601 UTC timestamp")
    location: str = Field("Rotterdam", description="Primary city location")
    station_name: str = Field(..., description="Primary observation station name")
    station_id: int = Field(..., description="Primary observation station ID")
    temperature: Optional[float] = Field(None, description="Current air temperature in °C")
    feeltemperature: Optional[float] = Field(None, description="Feels-like temperature in °C")
    humidity: Optional[float] = Field(None, description="Relative humidity %")
    airpressure: Optional[float] = Field(None, description="Air pressure in hPa")
    weather_description: str = Field(..., description="Dutch weather description")
    icon_url: Optional[str] = Field(None, description="Standard weather icon URL")
    full_icon_url: Optional[str] = Field(None, description="High-resolution weather icon URL")
    wind: Dict[str, Any] = Field(..., description="Wind metrics (speed_ms, speed_kmh, bft, gusts_ms, gusts_kmh, direction, degrees)")
    precipitation: Dict[str, Any] = Field(..., description="Rain nowcast metrics (current_mm_h, currently_raining, will_rain_in_2h, first_rain_in_minutes, max_expected_mm_h)")
    summary: str = Field(..., description="Concise human-readable live summary in Dutch")
    stations: List[Dict[str, Any]] = Field(..., description="Key metrics for all Rotterdam regional stations")
    radar_latest_tile_url: Optional[str] = Field(None, description="MapLibre tile URL for latest rain radar frame")
