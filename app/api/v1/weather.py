"""Weather, Precipitation Nowcast & Rain Radar API router (/api/v1/weather)."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.cache.redis_client import get_cached_json, set_cached_json
from app.schemas.weather import (
    LiveWeatherOverview,
    RainForecastResponse,
    WeatherStationsFeatureCollection,
    WeatherStationFeature,
    WeatherRadarResponse,
)
from app.ingestion.weather_harvester import (
    RotterdamWeatherHarvester,
    ROTTERDAM_DEFAULT_LAT,
    ROTTERDAM_DEFAULT_LON,
)

router = APIRouter(prefix="/weather", tags=["Live Weather & Rain Radar"])

_harvester = RotterdamWeatherHarvester()


@router.get(
    "/live",
    response_model=LiveWeatherOverview,
    summary="Instant overview of Rotterdam live weather and precipitation",
)
async def get_live_weather() -> LiveWeatherOverview:
    """
    Get a unified, instant overview of current Rotterdam weather:
    - Temperature, feels-like, condition icon and description.
    - Wind speed (Bft and km/h), direction, gusts.
    - Rain nowcast status (currently raining, next expected rain in X minutes).
    - Natural language summary in Dutch.
    Served in < 5ms directly from Redis cache.
    """
    cache_key = "weather:live:rotterdam"
    cached = await get_cached_json(cache_key)
    if cached:
        return LiveWeatherOverview.model_validate(cached)

    # Cold-start fallback: execute harvest on demand and cache
    await _harvester.fetch_weather_stations()
    overview = await get_cached_json(cache_key)
    if overview:
        return LiveWeatherOverview.model_validate(overview)

    # Fallback to fresh harvest
    res = await _harvester.fetch_weather_stations()
    cached = await get_cached_json(cache_key)
    if cached:
        return LiveWeatherOverview.model_validate(cached)

    raise HTTPException(status_code=503, detail="Weather telemetry temporarily unavailable")


@router.get(
    "/rain-forecast",
    response_model=RainForecastResponse,
    summary="Hyper-local 2-hour minute-by-minute rain nowcast",
)
async def get_rain_forecast(
    lat: float = Query(
        ROTTERDAM_DEFAULT_LAT,
        ge=50.0,
        le=54.0,
        description="Latitude (default: 51.9244 Rotterdam)",
    ),
    lon: float = Query(
        ROTTERDAM_DEFAULT_LON,
        ge=3.0,
        le=7.5,
        description="Longitude (default: 4.4777 Rotterdam)",
    ),
) -> RainForecastResponse:
    """
    Get hyper-local 2-hour minute-by-minute rain nowcast for Rotterdam coordinates.
    Converts official Buienradar radar reflectivity into exact rain rates in mm/h.
    """
    cache_key = f"weather:rain:nowcast:{round(lat, 2)}:{round(lon, 2)}"
    cached = await get_cached_json(cache_key)
    if cached:
        return RainForecastResponse.model_validate(cached)

    # Fetch on demand
    data = await _harvester.fetch_rain_nowcast(lat=lat, lon=lon)
    return RainForecastResponse.model_validate(data)


@router.get(
    "/radar",
    response_model=WeatherRadarResponse,
    summary="MapLibre-ready Animated Rain Radar Tile Stream",
)
async def get_weather_radar() -> WeatherRadarResponse:
    """
    Get RainViewer animated weather radar tile timeline for MapLibre GL raster layers.
    Returns chronological past and nowcast radar frame timestamps with Slippy tile URLs:
    https://tilecache.rainviewer.com/v2/radar/{path}/512/{z}/{x}/{y}/2/1_1.png
    """
    cache_key = "weather:radar:frames"
    cached = await get_cached_json(cache_key)
    if cached:
        return WeatherRadarResponse.model_validate(cached)

    data = await _harvester.fetch_radar_frames()
    return WeatherRadarResponse.model_validate(data)


@router.get(
    "/stations",
    response_model=WeatherStationsFeatureCollection,
    summary="Official KNMI weather observation stations in Greater Rotterdam",
)
async def get_weather_stations(
    session: AsyncSession = Depends(get_db),
) -> WeatherStationsFeatureCollection:
    """
    Get real-time telemetry from official KNMI weather observation stations:
    - 6344: Rotterdam The Hague Airport (Zestienhoven) [Primary]
    - 6330: Hoek van Holland [Coastal / Port]
    - 6343: Rotterdam Geulhaven [Port / Industrial]
    """
    cache_key = "weather:stations:all"
    cached = await get_cached_json(cache_key)
    if cached:
        return WeatherStationsFeatureCollection.model_validate(cached)

    data = await _harvester.fetch_weather_stations()
    return WeatherStationsFeatureCollection.model_validate(data)


@router.get(
    "/stations/{station_id}",
    response_model=WeatherStationFeature,
    summary="Get single KNMI weather station by ID",
)
async def get_weather_station(
    station_id: int,
    session: AsyncSession = Depends(get_db),
) -> WeatherStationFeature:
    """Get single KNMI observation station by ID (6344, 6330, 6343)."""
    cache_key = f"weather:stations:{station_id}"
    cached = await get_cached_json(cache_key)
    if cached:
        return WeatherStationFeature.model_validate(cached)

    # Refresh stations and check again
    await _harvester.fetch_weather_stations()
    cached = await get_cached_json(cache_key)
    if cached:
        return WeatherStationFeature.model_validate(cached)

    raise HTTPException(status_code=404, detail=f"Weather station {station_id} not found")
