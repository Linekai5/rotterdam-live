"""Pydantic schemas for Weather, Precipitation Nowcast, Station Telemetry & Radar Tiles."""
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class RainTimelineItem(BaseModel):
    """Minute-by-minute rain nowcast item."""
    time: str = Field(..., description="Timestamp in HH:MM format")
    intensity_mm_h: float = Field(..., description="Precipitation rate in mm/hour")
    valid_at: Optional[str] = None
    raw_value: int = Field(..., description="Raw Buienradar string value (000-255)")


class RainForecastResponse(BaseModel):
    """Hyper-local 2-hour rain nowcast response."""
    location: Dict[str, float] = Field(..., description="Target coordinates {'lat': float, 'lon': float}")
    generated_at: str = Field(..., description="Generation timestamp in ISO 8601 UTC")
    status: Literal["fresh", "stale", "unavailable"] = "unavailable"
    will_rain_in_2h: Optional[bool] = Field(..., description="True if rain is expected within the next 2 hours")
    max_intensity_mm_h: Optional[float] = Field(..., description="Peak precipitation intensity expected in next 2 hours")
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


class SolarPosition(BaseModel):
    """Real-time astronomical solar position for Rotterdam (51.922°N, 4.479°E)."""
    latitude: float = Field(51.922, description="Reference latitude in degrees")
    longitude: float = Field(4.479, description="Reference longitude in degrees")
    azimuth_deg: float = Field(..., description="Solar azimuth angle in degrees (0=N, 90=E, 180=S, 270=W)")
    elevation_deg: float = Field(..., description="Solar elevation angle above horizon in degrees (-90 to +90)")
    zenith_deg: float = Field(..., description="Solar zenith angle in degrees")
    is_day: int = Field(..., description="1 if sun is above horizon, 0 at night")
    daylight_phase: str = Field(..., description="Current lighting phase: night | twilight | golden_hour | day")
    sun_vector: List[float] = Field(..., description="Normalized 3D light direction vector [x_east, y_north, z_up]")
    shadow_offset_factor: List[float] = Field(
        ...,
        description="Projected ground cloud shadow offset multiplier [dx, dy] = cot(elev) * (sin(az), cos(az))",
    )


class SpatialWeatherNodeProperties(BaseModel):
    """Meteorological telemetry for one node of the 12-point Rotterdam Island micro-grid."""
    node_id: int = Field(..., description="1-based node index (1..12)")
    node_index: int = Field(..., description="0-based shader array index (0..11)")
    id: str = Field(..., description="Unique grid node slug identifier")
    name: str = Field(..., description="Grid node neighborhood/sector name")
    district: str = Field(..., description="Rotterdam municipal district or sector")
    zone: str = Field(..., description="Micro-climate zone: coastal | harbor | river | urban | inland")
    lat: float = Field(..., description="Node latitude (WGS84)")
    lon: float = Field(..., description="Node longitude (WGS84)")
    timestamp: str = Field(..., description="Observation/model ISO 8601 timestamp")
    cloud_cover: float = Field(..., description="Total cloud cover (%)")
    cloud_cover_low: float = Field(..., description="Low-altitude cloud deck 0-2km (%)")
    cloud_cover_mid: float = Field(..., description="Mid-altitude cloud deck 2-6km (%)")
    cloud_cover_high: float = Field(..., description="High-altitude cirrus deck >6km (%)")
    precipitation: float = Field(..., description="Total precipitation rate (mm/h)")
    rain: float = Field(..., description="Stratiform rain rate (mm/h)")
    showers: float = Field(..., description="Convective shower rate (mm/h)")
    snowfall: float = Field(..., description="Snowfall rate (cm/h)")
    weather_code: int = Field(..., description="WMO meteorological weather code")
    weather_description: str = Field(..., description="Human-readable Dutch weather description")
    wind_speed_10m: float = Field(..., description="10m wind speed (km/h)")
    wind_speed_ms: float = Field(..., description="10m wind speed (m/s)")
    wind_direction_10m: int = Field(..., description="10m wind direction in degrees (0-360)")
    wind_gusts_10m: float = Field(..., description="10m wind gusts (km/h)")
    wind_gusts_ms: float = Field(..., description="10m wind gusts (m/s)")
    wind_u: float = Field(..., description="Eastward wind vector component u (m/s)")
    wind_v: float = Field(..., description="Northward wind vector component v (m/s)")
    temperature_2m: float = Field(..., description="2m air temperature (°C)")
    apparent_temperature: float = Field(..., description="Apparent / feels-like temperature (°C)")
    relative_humidity_2m: float = Field(..., description="2m relative humidity (%)")
    visibility: float = Field(..., description="Horizontal visibility (meters)")
    surface_pressure: float = Field(..., description="Surface barometric pressure (hPa)")
    cape: float = Field(..., description="Convective Available Potential Energy (J/kg)")
    is_day: int = Field(..., description="Daylight flag (1=day, 0=night)")
    storm_intensity: float = Field(..., description="Normalized WebGL shader storm intensity [0.0..1.0]")
    fog_density: float = Field(..., description="Normalized WebGL shader coastal/river fog density [0.0..1.0]")
    lightning_active: bool = Field(False, description="True if thunderstorm / sheet lightning is active in cell")


class SpatialWeatherNodeFeature(BaseModel):
    """RFC 7946 GeoJSON Feature for a spatial weather grid node."""
    type: Literal["Feature"] = "Feature"
    id: str = Field(..., description="Feature identifier (e.g. weather-grid-node-1)")
    geometry: Dict[str, Any] = Field(..., description="GeoJSON Point geometry [lon, lat]")
    properties: SpatialWeatherNodeProperties


class SpatialWindField(BaseModel):
    """City-wide aggregated wind vector field and coastal-to-inland shear metrics."""
    mean_speed_kmh: float = Field(..., description="Mean 10m wind speed across Rotterdam (km/h)")
    mean_speed_ms: float = Field(..., description="Mean 10m wind speed across Rotterdam (m/s)")
    max_gusts_kmh: float = Field(..., description="Maximum wind gusts across the 12-node grid (km/h)")
    mean_direction_deg: int = Field(..., description="Vector-averaged wind direction (degrees)")
    direction_compass: str = Field(..., description="Compass cardinal direction (e.g. ZW, WNW)")
    mean_u_ms: float = Field(..., description="Mean eastward wind component u (m/s)")
    mean_v_ms: float = Field(..., description="Mean northward wind component v (m/s)")
    coastal_speed_kmh: float = Field(..., description="Mean wind speed at coastal Maasvlakte/Hoek van Holland (km/h)")
    inland_speed_kmh: float = Field(..., description="Mean wind speed at inland districts (km/h)")
    coastal_inland_gradient_kmh: float = Field(..., description="Wind speed delta between North Sea coast and inland (km/h)")


class StormFlags(BaseModel):
    """Active atmospheric hazard flags for WebGL storm rendering & tactical HUD."""
    is_storm: bool = Field(..., description="True if heavy precipitation (>=4mm/h), high gusts, or WMO storm code")
    is_thunderstorm: bool = Field(..., description="True if WMO thunderstorm (95, 96, 99) or high CAPE")
    lightning_probability: Optional[float] = Field(..., description="Probability [0.0..1.0] of in-cloud sheet lightning")
    coastal_squall: bool = Field(..., description="True if coastal nodes experience squall conditions")
    fog_advisory: bool = Field(..., description="True if visibility < 3000m or relative humidity > 92%")
    active_rain_nodes: int = Field(..., description="Number of grid nodes (out of 12) currently experiencing precipitation")
    max_cape_j_kg: float = Field(..., description="Peak CAPE across the 12-node mesh (J/kg)")
    max_precipitation_mm_h: float = Field(..., description="Peak precipitation rate across the 12-node mesh (mm/h)")
    max_wind_gusts_kmh: float = Field(..., description="Peak wind gusts across the 12-node mesh (km/h)")


class SpatialWeatherCitySummary(BaseModel):
    """Aggregated city-wide summary metrics across all 12 Rotterdam Island grid nodes."""
    temperature_avg_c: float = Field(..., description="Mean temperature across Rotterdam (°C)")
    temperature_min_c: float = Field(..., description="Minimum node temperature (°C)")
    temperature_max_c: float = Field(..., description="Maximum node temperature (°C)")
    cloud_cover_avg_pct: float = Field(..., description="Mean total cloud cover (%)")
    cloud_cover_low_avg_pct: float = Field(..., description="Mean low-deck cloud cover (%)")
    cloud_cover_mid_avg_pct: float = Field(..., description="Mean mid-deck cloud cover (%)")
    cloud_cover_high_avg_pct: float = Field(..., description="Mean high-deck cloud cover (%)")
    precipitation_avg_mm_h: float = Field(..., description="Mean precipitation rate (mm/h)")
    precipitation_max_mm_h: float = Field(..., description="Max precipitation rate (mm/h)")
    humidity_avg_pct: float = Field(..., description="Mean relative humidity (%)")
    visibility_min_m: float = Field(..., description="Minimum visibility across nodes (meters)")
    surface_pressure_avg_hpa: float = Field(..., description="Mean barometric pressure (hPa)")
    dominant_weather_code: int = Field(..., description="Most severe / dominant WMO weather code")
    dominant_weather_description: str = Field(..., description="Dutch description of dominant condition")


class SpatialWeatherGridResponse(BaseModel):
    """RFC 7946 GeoJSON FeatureCollection for the 12-point Rotterdam Spatial Weather Grid."""
    type: Literal["FeatureCollection"] = "FeatureCollection"
    generated_at: str = Field(..., description="ISO 8601 UTC generation timestamp")
    data_status: Literal["fresh", "stale"] = "stale"
    source: str = "Open-Meteo / KNMI HARMONIE model"
    observed_at: Optional[str] = None
    ttl_seconds: int = Field(120, description="Redis cache TTL in seconds")
    model: str = Field("knmi_harmonie_arome", description="Upstream numerical weather model")
    total_nodes: int = Field(12, description="Number of spatial grid nodes covering Rotterdam Island")
    features: List[SpatialWeatherNodeFeature] = Field(..., description="12 GeoJSON Point features for the weather mesh")
    grid_nodes: List[SpatialWeatherNodeProperties] = Field(..., description="Flat array of all 12 node telemetry payloads")
    city_summary: SpatialWeatherCitySummary = Field(..., description="Aggregated city-wide weather summary")
    wind_field: SpatialWindField = Field(..., description="City-wide wind vector field and coastal gradient")
    solar: SolarPosition = Field(..., description="Live Rotterdam solar azimuth, elevation, and shadow vectors")
    storm_flags: StormFlags = Field(..., description="Active storm, lightning, squall, and fog flags")


class LiveWeatherOverview(BaseModel):
    """Instant unified overview + 12-point GeoJSON Spatial Weather Grid of Rotterdam."""
    type: Literal["FeatureCollection"] = "FeatureCollection"
    generated_at: str = Field(..., description="ISO 8601 UTC timestamp")
    data_status: Literal["fresh", "stale"] = "stale"
    source: str = "Open-Meteo / KNMI HARMONIE model"
    observed_at: Optional[str] = None
    ttl_seconds: int = Field(120, description="Redis cache TTL in seconds")
    model: str = Field("knmi_harmonie_arome", description="Upstream NWP model identifier")
    location: str = Field("Rotterdam", description="Primary city location")
    station_name: str = Field(..., description="Primary observation station name")
    station_id: Optional[int] = Field(None, description="Primary observation station ID; null for model-only conditions")
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
    total_nodes: int = Field(12, description="Total nodes in the 12-point Rotterdam spatial weather mesh")
    features: List[SpatialWeatherNodeFeature] = Field(default_factory=list, description="12 GeoJSON Point features for the weather mesh")
    grid_nodes: List[SpatialWeatherNodeProperties] = Field(default_factory=list, description="12 spatial weather grid node payloads")
    city_summary: Optional[SpatialWeatherCitySummary] = Field(None, description="City-wide aggregated weather metrics")
    wind_field: Optional[SpatialWindField] = Field(None, description="Wind vector field and coastal gradient")
    solar: Optional[SolarPosition] = Field(None, description="Real-time Rotterdam solar azimuth and elevation")
    storm_flags: Optional[StormFlags] = Field(None, description="Storm, lightning, and coastal fog flags")

