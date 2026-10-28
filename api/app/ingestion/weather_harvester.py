"""Model weather, point observations/nowcasts, and radar metadata ingestion.

Data Sources:
1. Buienradar 2-hour Rain Nowcast (gpsgadget.buienradar.nl)
2. Buienradar & KNMI Official Observation Stations (data.buienradar.nl/2.0/feed/json)
3. RainViewer Open Radar API (api.rainviewer.com)
4. Open-Meteo KNMI model grid (api.open-meteo.com)
"""
import math
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import select

from app.ingestion.base import BaseIngestor
from app.logging import logger
from app.config import settings
from app.db.session import AsyncSessionLocal
from app.db.models import CityAmenity, LiveEvent
from app.services.spatial_service import find_district_for_point, upsert_live_event
from app.cache.redis_client import get_cached_json, set_cached_json
from app.schemas.weather import (
    RainTimelineItem,
    RainForecastResponse,
    WeatherStationProperties,
    WeatherStationFeature,
    WeatherStationsFeatureCollection,
    RadarFrame,
    WeatherRadarResponse,
    LiveWeatherOverview,
)

# Rotterdam Coordinates
ROTTERDAM_DEFAULT_LAT = 51.9244
ROTTERDAM_DEFAULT_LON = 4.4777
ROTTERDAM_SOLAR_LAT = 51.922
ROTTERDAM_SOLAR_LON = 4.479

# 12-Point Spatial Weather Micro-Grid Covering Rotterdam Island (West Coast -> East Inland)
ROTTERDAM_WEATHER_GRID_NODES: List[Dict[str, Any]] = [
    {
        "node_id": 1,
        "node_index": 0,
        "id": "weather-grid-node-1",
        "name": "Maasvlakte West",
        "district": "Botlek-Europoort-Maasvlakte",
        "zone": "coastal",
        "lat": 51.958,
        "lon": 3.985,
    },
    {
        "node_id": 2,
        "node_index": 1,
        "id": "weather-grid-node-2",
        "name": "Hoek van Holland",
        "district": "Hoek van Holland",
        "zone": "coastal",
        "lat": 51.977,
        "lon": 4.133,
    },
    {
        "node_id": 3,
        "node_index": 2,
        "id": "weather-grid-node-3",
        "name": "Rozenburg / Botlek",
        "district": "Rozenburg",
        "zone": "harbor",
        "lat": 51.888,
        "lon": 4.245,
    },
    {
        "node_id": 4,
        "node_index": 3,
        "id": "weather-grid-node-4",
        "name": "Vlaardingen / Schiedam Border",
        "district": "Nieuw-Mathenesse",
        "zone": "river",
        "lat": 51.915,
        "lon": 4.355,
    },
    {
        "node_id": 5,
        "node_index": 4,
        "id": "weather-grid-node-5",
        "name": "Pernis / Waalhaven",
        "district": "Pernis",
        "zone": "harbor",
        "lat": 51.885,
        "lon": 4.415,
    },
    {
        "node_id": 6,
        "node_index": 5,
        "id": "weather-grid-node-6",
        "name": "Delfshaven / Noord",
        "district": "Delfshaven",
        "zone": "urban",
        "lat": 51.928,
        "lon": 4.448,
    },
    {
        "node_id": 7,
        "node_index": 6,
        "id": "weather-grid-node-7",
        "name": "Rotterdam Centrum",
        "district": "Rotterdam Centrum",
        "zone": "urban",
        "lat": 51.922,
        "lon": 4.479,
    },
    {
        "node_id": 8,
        "node_index": 7,
        "id": "weather-grid-node-8",
        "name": "Charlois / Zuiderpark",
        "district": "Charlois",
        "zone": "urban",
        "lat": 51.882,
        "lon": 4.482,
    },
    {
        "node_id": 9,
        "node_index": 8,
        "id": "weather-grid-node-9",
        "name": "Kralingen / Crooswijk",
        "district": "Kralingen-Crooswijk",
        "zone": "inland",
        "lat": 51.932,
        "lon": 4.522,
    },
    {
        "node_id": 10,
        "node_index": 9,
        "id": "weather-grid-node-10",
        "name": "Hillegersberg / Schiebroek",
        "district": "Hillegersberg-Schiebroek",
        "zone": "inland",
        "lat": 51.962,
        "lon": 4.485,
    },
    {
        "node_id": 11,
        "node_index": 10,
        "id": "weather-grid-node-11",
        "name": "Feijenoord / IJsselmonde",
        "district": "Feijenoord",
        "zone": "river",
        "lat": 51.888,
        "lon": 4.545,
    },
    {
        "node_id": 12,
        "node_index": 11,
        "id": "weather-grid-node-12",
        "name": "Prins Alexander / Nesselande",
        "district": "Prins Alexander",
        "zone": "inland",
        "lat": 51.965,
        "lon": 4.575,
    },
]

# Targeted KNMI Observation Stations in Greater Rotterdam
TARGET_KNMI_STATIONS = {
    6344: {
        "name": "Rotterdam The Hague Airport (Zestienhoven)",
        "is_primary": True,
        "default_district": "Overschie",
    },
    6330: {
        "name": "Hoek van Holland",
        "is_primary": False,
        "default_district": "Hoek van Holland",
    },
    6343: {
        "name": "Rotterdam Geulhaven",
        "is_primary": False,
        "default_district": "Botlek-Europoort-Maasvlakte",
    },
}

BUIENRADAR_RAIN_URL = "https://gpsgadget.buienradar.nl/data/raintext/"
BUIENRADAR_FEED_URL = "https://data.buienradar.nl/2.0/feed/json"
RAINVIEWER_RADAR_URL = "https://api.rainviewer.com/public/weather-maps.json"
OPEN_METEO_KNMI_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_CURRENT_FIELDS = (
    "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,"
    "precipitation,rain,showers,snowfall,weather_code,"
    "cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,"
    "surface_pressure,wind_speed_10m,wind_direction_10m,wind_gusts_10m,"
    "visibility,cape"
)


def wmo_weather_description_nl(code: int) -> str:
    """Map WMO weather code to Dutch weather condition string."""
    mapping = {
        0: "Onbewolkt",
        1: "Overwegend helder",
        2: "Half bewolkt",
        3: "Geheel bewolkt",
        45: "Mist",
        48: "Aanvriezende mist",
        51: "Lichte motregen",
        53: "Matige motregen",
        55: "Dichte motregen",
        56: "Lichte ijzel",
        57: "Zware ijzel",
        61: "Lichte regen",
        63: "Matige regen",
        65: "Zware regen",
        66: "Lichte ijsregen",
        67: "Zware ijsregen",
        71: "Lichte sneeuwval",
        73: "Matige sneeuwval",
        75: "Zware sneeuwval",
        77: "Korrelsneeuw",
        80: "Lichte regenbui",
        81: "Matige regenbui",
        82: "Zware regenbui",
        85: "Sneeuwbui",
        86: "Zware sneeuwbui",
        95: "Onweer",
        96: "Onweer met hagel",
        99: "Zwaar onweer met hagel",
    }
    return mapping.get(int(code or 0), "Wisselend bewolkt")


def degrees_to_compass_nl(deg: float) -> str:
    """Convert meteorological wind direction degrees (0-360) to Dutch 16-wind compass string."""
    dirs = [
        "N", "NNO", "NO", "ONO",
        "O", "OZO", "ZO", "ZZO",
        "Z", "ZZW", "ZW", "WZW",
        "W", "WNW", "NW", "NNW",
    ]
    idx = int(round((deg % 360) / 22.5)) % 16
    return dirs[idx]


def kmh_to_beaufort(kmh: float) -> int:
    """Convert wind speed in km/h to Beaufort scale (0-12)."""
    thresholds = [1, 6, 12, 20, 29, 39, 50, 62, 75, 89, 103, 118]
    for bft, limit in enumerate(thresholds):
        if kmh < limit:
            return bft
    return 12


def calculate_solar_position(
    dt: Optional[datetime] = None,
    lat: float = ROTTERDAM_SOLAR_LAT,
    lon: float = ROTTERDAM_SOLAR_LON,
) -> Dict[str, Any]:
    """
    Calculate real-time Solar Azimuth & Elevation Angle for Rotterdam (51.922°N, 4.479°E)
    using NOAA solar position equations.
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    # Day of year & fractional hour in UTC
    day_of_year = dt.timetuple().tm_yday
    utc_hour = dt.hour + dt.minute / 60.0 + dt.second / 3600.0

    # Fractional year gamma (radians)
    gamma = 2.0 * math.pi / 365.0 * (day_of_year - 1 + (utc_hour - 12.0) / 24.0)

    # Equation of time (minutes)
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2.0 * gamma)
        - 0.040849 * math.sin(2.0 * gamma)
    )

    # Solar declination angle (radians)
    decl = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2.0 * gamma)
        + 0.000907 * math.sin(2.0 * gamma)
        - 0.002697 * math.cos(3.0 * gamma)
        + 0.00148 * math.sin(3.0 * gamma)
    )

    # True solar time (minutes) and hour angle ha (radians)
    time_offset = eqtime + 4.0 * lon
    tst = (utc_hour * 60.0 + time_offset) % 1440.0
    ha_deg = (tst / 4.0) - 180.0
    ha = math.radians(ha_deg)
    lat_rad = math.radians(lat)

    # Cosine of solar zenith angle
    cos_zenith = (
        math.sin(lat_rad) * math.sin(decl)
        + math.cos(lat_rad) * math.cos(decl) * math.cos(ha)
    )
    cos_zenith = max(-1.0, min(1.0, cos_zenith))
    zenith_rad = math.acos(cos_zenith)
    zenith_deg = math.degrees(zenith_rad)
    elevation_deg = 90.0 - zenith_deg

    # Solar azimuth (0=North, 90=East, 180=South, 270=West)
    sin_zenith = math.sin(zenith_rad)
    if abs(sin_zenith) > 1e-5:
        cos_az = (math.sin(decl) - math.sin(lat_rad) * cos_zenith) / (
            math.cos(lat_rad) * sin_zenith
        )
        cos_az = max(-1.0, min(1.0, cos_az))
        az_rad = math.acos(cos_az)
        azimuth_deg = math.degrees(az_rad)
        if ha_deg > 0.0:
            azimuth_deg = (360.0 - azimuth_deg) % 360.0
    else:
        azimuth_deg = 180.0

    is_day = 1 if elevation_deg > -0.833 else 0
    if elevation_deg < -6.0:
        daylight_phase = "night"
    elif elevation_deg < 0.0:
        daylight_phase = "twilight"
    elif elevation_deg < 12.0:
        daylight_phase = "golden_hour"
    else:
        daylight_phase = "day"

    # 3D unit vector pointing toward the sun [east, north, up]
    elev_clamped_rad = math.radians(max(8.0, abs(elevation_deg)))
    az_rad_full = math.radians(azimuth_deg)
    cos_el = math.cos(math.radians(elevation_deg))
    sun_vec = [
        round(cos_el * math.sin(az_rad_full), 4),
        round(cos_el * math.cos(az_rad_full), 4),
        round(math.sin(math.radians(elevation_deg)), 4),
    ]

    # Projected ground cloud shadow offset factor: cot(theta_sun) * (sin(phi_sun), cos(phi_sun))
    # Clamped to max cot(12 deg) ~ 4.7 so low horizon sun doesn't stretch shadows to infinity
    cot_theta = min(3.8, max(0.25, 1.0 / math.tan(elev_clamped_rad)))
    shadow_offset_factor = [
        round(-cot_theta * math.sin(az_rad_full), 4),
        round(-cot_theta * math.cos(az_rad_full), 4),
    ]

    return {
        "latitude": lat,
        "longitude": lon,
        "azimuth_deg": round(azimuth_deg, 2),
        "elevation_deg": round(elevation_deg, 2),
        "zenith_deg": round(zenith_deg, 2),
        "is_day": is_day,
        "daylight_phase": daylight_phase,
        "sun_vector": sun_vec,
        "shadow_offset_factor": shadow_offset_factor,
    }


def raw_rain_to_mm_h(raw_str: str) -> float:
    """
    Convert 3-digit Buienradar string value (000-255) to precipitation intensity in mm/h.
    Formula: intensity (mm/h) = 10^((value - 109) / 32)
    Note: value 0 = 0.0 mm/h.
    """
    try:
        val = int(raw_str)
    except (ValueError, TypeError):
        return 0.0

    if val <= 0:
        return 0.0
    return round(10 ** ((val - 109) / 32), 2)


class RotterdamWeatherHarvester(BaseIngestor):
    """Validate and cache the model grid, station telemetry, nowcasts and radar metadata."""

    def __init__(self):
        super().__init__(name="rotterdam_weather_harvester", timeout_seconds=15.0)

    async def ingest(self) -> Dict[str, Any]:
        """Run all weather harvesting tasks and refresh databases & Redis caches."""
        rain_result = await self.fetch_rain_nowcast()
        stations_result = await self.fetch_weather_stations()
        radar_result = await self.fetch_radar_frames()
        grid_result = await self.fetch_spatial_weather_grid()

        return {
            "rain_nowcast_generated": rain_result.get("generated_at"),
            "stations_count": stations_result.get("total_stations", 0),
            "radar_past_frames": len(radar_result.get("past_frames", [])),
            "spatial_grid_nodes": grid_result.get("total_nodes", 0),
        }

    # =========================================================================
    # 1. BUIENRADAR 2-HOUR RAIN NOWCAST
    # =========================================================================
    async def fetch_rain_nowcast(
        self, lat: float = ROTTERDAM_DEFAULT_LAT, lon: float = ROTTERDAM_DEFAULT_LON
    ) -> Dict[str, Any]:
        """
        Fetch minute-by-minute 2-hour rain nowcast from Buienradar.
        Converts raw 3-digit values to mm/h and caches in Redis with 5-minute TTL.
        """
        cache_key = f"weather:rain:nowcast:{round(lat, 2)}:{round(lon, 2)}"
        client = await self.get_client()

        params = {"lat": f"{round(lat, 2)}", "lon": f"{round(lon, 2)}"}
        timeline: List[Dict[str, Any]] = []

        try:
            resp = await client.get(
                BUIENRADAR_RAIN_URL,
                params=params,
                follow_redirects=True,
                headers={"User-Agent": "RotterdamLive/1.5"},
            )

            if resp.status_code == 200:
                raw_lines = resp.text.strip().split("\n")
                for line in raw_lines:
                    if "|" in line:
                        parts = line.strip().split("|")
                        if len(parts) == 2:
                            val_str, t_str = parts[0].strip(), parts[1].strip()
                            datetime.strptime(t_str, "%H:%M")
                            raw_val = int(val_str)
                            if not 0 <= raw_val <= 255:
                                raise ValueError("Invalid rain intensity")
                            intensity = raw_rain_to_mm_h(val_str)
                            timeline.append({
                                "time": t_str,
                                "intensity_mm_h": intensity,
                                "raw_value": raw_val,
                            })
            else:
                logger.warning(
                    "Buienradar raintext returned HTTP {} for lat={}, lon={}",
                    resp.status_code,
                    lat,
                    lon,
                )
        except Exception as e:
            logger.warning("Failed fetching Buienradar rain nowcast: {}", e)
            timeline = []

        now = datetime.now(timezone.utc)
        if not timeline:
            previous = await get_cached_json(cache_key + ":last_good")
            if previous:
                return {**previous, "status": "stale", "summary": "Regenverwachting tijdelijk niet bijgewerkt"}
            return {
                "location": {"lat": lat, "lon": lon}, "generated_at": now.isoformat(),
                "status": "unavailable", "will_rain_in_2h": None,
                "max_intensity_mm_h": None, "first_rain_in_minutes": None,
                "summary": "Regenverwachting tijdelijk niet beschikbaar", "timeline": [],
            }

        # Buienradar returns local clock times. Resolve dates across midnight,
        # then publish unambiguous UTC timestamps and use actual lead times.
        local_now = now.astimezone(ZoneInfo("Europe/Amsterdam"))
        previous_time = None
        for item in timeline:
            hour, minute = map(int, item["time"].split(":"))
            slot = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if slot < local_now - timedelta(minutes=15):
                slot += timedelta(days=1)
            if previous_time and slot < previous_time:
                slot += timedelta(days=1)
            previous_time = slot
            item["valid_at"] = slot.astimezone(timezone.utc).isoformat()

        will_rain_in_2h = any(item["intensity_mm_h"] > 0 for item in timeline)
        max_intensity = max((item["intensity_mm_h"] for item in timeline), default=0.0)
        currently_raining = (timeline[0]["intensity_mm_h"] > 0) if timeline else False

        # Calculate minutes until first rain
        first_rain_in_minutes: Optional[int] = None
        if currently_raining:
            first_rain_in_minutes = 0
        elif will_rain_in_2h:
            for idx, item in enumerate(timeline):
                if item["intensity_mm_h"] > 0:
                    first_rain_in_minutes = max(0, round((datetime.fromisoformat(item["valid_at"]) - now).total_seconds() / 60))
                    break

        # Generate human-readable Dutch summary
        if currently_raining:
            current_mm = timeline[0]["intensity_mm_h"]
            summary = f"Regen in Rotterdam ({current_mm} mm/u), piek van {max_intensity} mm/u verwacht komende 2 uur"
        elif will_rain_in_2h and first_rain_in_minutes is not None:
            summary = f"Droog momenteel, regen verwacht over circa {first_rain_in_minutes} minuten (tot {max_intensity} mm/u)"
        else:
            summary = "Geen neerslag verwacht in Rotterdam komende 2 uur (droog)"

        response_data = {
            "location": {"lat": round(lat, 4), "lon": round(lon, 4)},
            "generated_at": now.isoformat(),
            "status": "fresh",
            "will_rain_in_2h": will_rain_in_2h,
            "max_intensity_mm_h": max_intensity,
            "first_rain_in_minutes": first_rain_in_minutes,
            "summary": summary,
            "timeline": timeline,
        }

        # Cache in Redis with 5-minute TTL (300 seconds)
        await set_cached_json(cache_key, response_data, ttl_seconds=300)
        await set_cached_json(cache_key + ":last_good", response_data, ttl_seconds=86400)
        if abs(lat - ROTTERDAM_DEFAULT_LAT) < 0.05 and abs(lon - ROTTERDAM_DEFAULT_LON) < 0.05:
            await set_cached_json("weather:rain:nowcast:rotterdam", response_data, ttl_seconds=300)

        return response_data

    # =========================================================================
    # 2. BUIENRADAR & KNMI OBSERVATION STATIONS
    # =========================================================================
    async def fetch_weather_stations(self) -> Dict[str, Any]:
        """
        Fetch real-time KNMI weather station telemetry for Greater Rotterdam:
        - Station 6344: Rotterdam The Hague Airport (Zestienhoven) [Primary]
        - Station 6330: Hoek van Holland [Coastal / Port]
        - Station 6343: Rotterdam Geulhaven [Port / Industrial]
        Upserts into PostgreSQL city_amenities and live_events, and caches in Redis.
        """
        client = await self.get_client()
        now = datetime.now(timezone.utc)
        features: List[Dict[str, Any]] = []
        primary_station_data: Optional[Dict[str, Any]] = None

        try:
            resp = await client.get(
                BUIENRADAR_FEED_URL,
                headers={"User-Agent": "RotterdamLive/1.5"},
            )
            if resp.status_code == 200:
                feed = resp.json()
                raw_stations = feed.get("actual", {}).get("stationmeasurements", [])
            else:
                logger.warning("Buienradar feed returned status {}", resp.status_code)
                raw_stations = []
        except Exception as e:
            logger.warning("Failed fetching Buienradar station feed: {}", e)
            raw_stations = []

        if not any(s.get("stationid") in TARGET_KNMI_STATIONS for s in raw_stations):
            previous = await get_cached_json("weather:stations:last_good")
            features = previous.get("features", []) if previous else []
            primary = next((f["properties"] for f in features if f["properties"].get("is_primary")), None)
            await self._build_and_cache_live_overview(primary, features)
            return previous or {"type": "FeatureCollection", "features": [], "total_stations": 0}

        async with AsyncSessionLocal() as session:
            for s in raw_stations:
                st_id = s.get("stationid")
                if st_id not in TARGET_KNMI_STATIONS:
                    continue

                meta = TARGET_KNMI_STATIONS[st_id]
                lat = float(s.get("lat", 0.0))
                lon = float(s.get("lon", 0.0))

                # PostGIS district resolution
                resolved_district = await find_district_for_point(lon, lat, session)
                district = resolved_district or meta["default_district"]

                temp = s.get("temperature")
                feel_temp = s.get("feeltemperature")
                ground_temp = s.get("groundtemperature")
                humidity = s.get("humidity")
                pressure = s.get("airpressure")
                wind_ms = s.get("windspeed")
                wind_bft = s.get("windspeedBft")
                wind_gusts_ms = s.get("windgusts")
                wind_dir = s.get("winddirection")
                wind_deg = s.get("winddirectiondegrees")
                precipitation = s.get("precipitation")
                rain_1h = s.get("rainFallLastHour")
                rain_24h = s.get("rainFallLast24Hour")
                visibility = s.get("visibility")
                sunpower = s.get("sunpower")
                description = s.get("weatherdescription") or "Onbekend"
                icon_url = s.get("iconurl")
                full_icon_url = s.get("fullIconUrl")

                wind_kmh = round(wind_ms * 3.6, 1) if wind_ms is not None else None
                wind_gusts_kmh = round(wind_gusts_ms * 3.6, 1) if wind_gusts_ms is not None else None

                props = {
                    "station_id": st_id,
                    "station_name": meta["name"],
                    "regio": s.get("regio", "Rotterdam"),
                    "district": district,
                    "is_primary": meta["is_primary"],
                    "timestamp": datetime.fromisoformat(s["timestamp"]).replace(tzinfo=ZoneInfo("Europe/Amsterdam")).astimezone(timezone.utc).isoformat(),
                    "temperature": temp,
                    "feeltemperature": feel_temp,
                    "groundtemperature": ground_temp,
                    "humidity": humidity,
                    "airpressure": pressure,
                    "windspeed_ms": wind_ms,
                    "windspeed_kmh": wind_kmh,
                    "windspeed_bft": wind_bft,
                    "windgusts_ms": wind_gusts_ms,
                    "windgusts_kmh": wind_gusts_kmh,
                    "winddirection": wind_dir,
                    "winddirectiondegrees": wind_deg,
                    "precipitation_mm_h": precipitation,
                    "rainfall_last_hour": rain_1h,
                    "rainfall_last_24h": rain_24h,
                    "visibility_m": visibility,
                    "sunpower": sunpower,
                    "weather_description": description,
                    "icon_url": icon_url,
                    "full_icon_url": full_icon_url,
                }

                feat = {
                    "type": "Feature",
                    "id": f"weather-station-{st_id}",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [lon, lat],
                    },
                    "properties": props,
                }
                features.append(feat)

                if meta["is_primary"]:
                    primary_station_data = props

                # Cache individual station in Redis
                await set_cached_json(f"weather:stations:{st_id}", feat, ttl_seconds=600)

                # Upsert into PostgreSQL city_amenities
                amenity_id = f"weather-station-{st_id}"
                point_geom = from_shape(Point(lon, lat), srid=4326)

                stmt = select(CityAmenity).where(CityAmenity.id == amenity_id)
                res = await session.execute(stmt)
                existing = res.scalar_one_or_none()

                if existing:
                    existing.name = meta["name"]
                    existing.district = district
                    existing.details = props
                    existing.geom = point_geom
                    existing.is_active = True
                    existing.updated_at = now
                else:
                    new_amenity = CityAmenity(
                        id=amenity_id,
                        category="amenity",
                        subcategory="weather_station",
                        name=meta["name"],
                        description=f"KNMI Weerstation {meta['name']} ({st_id})",
                        district=district,
                        details=props,
                        geom=point_geom,
                        is_active=True,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(new_amenity)

                # Upsert live event telemetry
                severity = 1
                if wind_bft and wind_bft >= 8:
                    severity = 4  # Storm
                elif wind_bft and wind_bft >= 6:
                    severity = 2  # Strong wind

                event_data = {
                    "id": f"weather-live-{st_id}",
                    "category": "environment",
                    "subcategory": "weather",
                    "severity": severity,
                    "timestamp": now,
                    "expires_at": now + timedelta(minutes=20),
                    "district": district,
                    "title": f"Weer {meta['name']}: {temp or '—'}°C, {description}",
                    "details": props,
                    "lon": lon,
                    "lat": lat,
                }
                await upsert_live_event(event_data, session)

            await session.commit()

        # Cache full stations FeatureCollection in Redis (10 min TTL)
        fc = {
            "type": "FeatureCollection",
            "features": features,
            "total_stations": len(features),
        }
        await set_cached_json("weather:stations:all", fc, ttl_seconds=600)
        await set_cached_json("weather:stations:last_good", fc, ttl_seconds=86400)

        # Build and cache unified LiveWeatherOverview
        await self._build_and_cache_live_overview(primary_station_data, features)

        return fc

    async def _build_and_cache_live_overview(
        self, primary_station: Optional[Dict[str, Any]], features: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Combine primary station telemetry, rain nowcast, and regional overview into sub-5ms live snapshot."""
        now = datetime.now(timezone.utc)

        # Get latest rain nowcast snapshot from Redis or generate
        rain_nowcast = await get_cached_json("weather:rain:nowcast:rotterdam")
        if not rain_nowcast:
            rain_nowcast = await self.fetch_rain_nowcast()

        primary = primary_station or (features[0]["properties"] if features else {})
        observation_time = primary.get("timestamp")
        if observation_time:
            observation_dt = datetime.fromisoformat(observation_time)
            if observation_dt.tzinfo is None:
                observation_dt = observation_dt.replace(tzinfo=ZoneInfo("Europe/Amsterdam"))
            if (now - observation_dt).total_seconds() > 1800:
                primary = {}

        def observed(key, fallback=None):
            value = primary.get(key)
            return fallback if value is None else value

        temp = primary.get("temperature")
        feel_temp = primary.get("feeltemperature")
        desc = observed("weather_description", "Bewolkt")
        wind_bft = observed("windspeed_bft", 3)
        wind_dir = observed("winddirection", "—")

        rain_will_rain = rain_nowcast.get("will_rain_in_2h", False)
        rain_minutes = rain_nowcast.get("first_rain_in_minutes")
        rain_max = rain_nowcast.get("max_intensity_mm_h") or 0.0
        is_raining = bool(rain_nowcast.get("timeline")) and rain_nowcast["timeline"][0]["intensity_mm_h"] > 0

        # Construct live summary sentence
        if is_raining:
            summary = f"{desc} in Rotterdam ({temp}°C), regenachtig ({rain_nowcast['timeline'][0]['intensity_mm_h']} mm/u)"
        elif rain_will_rain and rain_minutes is not None:
            summary = f"{desc} in Rotterdam ({temp}°C), droog komende {rain_minutes} minuten, daarna regen ({rain_max} mm/u)"
        else:
            summary = f"{desc} in Rotterdam ({temp}°C), droog komende 2 uur met matige wind ({wind_bft} Bft {wind_dir})"

        if rain_nowcast.get("status") != "fresh":
            summary = f"{desc} in Rotterdam; regenverwachting tijdelijk niet beschikbaar"

        stations_summary = [
            {
                "station_id": f["properties"]["station_id"],
                "name": f["properties"]["station_name"],
                "district": f["properties"]["district"],
                "temperature": f["properties"]["temperature"],
                "feeltemperature": f["properties"]["feeltemperature"],
                "windspeed_bft": f["properties"]["windspeed_bft"],
                "winddirection": f["properties"]["winddirection"],
                "weather_description": f["properties"]["weather_description"],
                "icon_url": f["properties"]["icon_url"],
            }
            for f in features
        ]

        radar_data = await get_cached_json("weather:radar:frames")
        latest_radar_url = (radar_data.get("latest_frame") or {}).get("tile_url") if radar_data else None

        # Ensure 12-node spatial weather grid is available for unified response
        spatial_grid = await get_cached_json("weather:spatial:grid")
        if not spatial_grid:
            spatial_grid = await self.fetch_spatial_weather_grid(sync_live_overview=False)

        city_sum = spatial_grid.get("city_summary", {})
        wind_fld = spatial_grid.get("wind_field", {})

        center = spatial_grid["grid_nodes"][6]
        if temp is None:
            temp = center["temperature_2m"]
        if feel_temp is None:
            feel_temp = center["apparent_temperature"]
        desc = observed("weather_description", center["weather_description"])
        wind_bft = observed("windspeed_bft", kmh_to_beaufort(center["wind_speed_10m"]))
        if not primary:
            summary = f"{desc} in Rotterdam ({temp}°C); {rain_nowcast['summary']}"

        overview = {
            "type": "FeatureCollection",
            "generated_at": now.isoformat(),
            "data_status": spatial_grid.get("data_status", "stale"),
            "source": "Open-Meteo / KNMI HARMONIE model",
            "observed_at": observation_time,
            "ttl_seconds": 120,
            "model": spatial_grid.get("model", "knmi_harmonie_arome"),
            "location": "Rotterdam",
            "station_name": primary.get("station_name", "Rotterdam Centrum (model)"),
            "station_id": primary.get("station_id"),
            "temperature": temp,
            "feeltemperature": feel_temp,
            "humidity": observed("humidity", city_sum.get("humidity_avg_pct")),
            "airpressure": observed("airpressure", city_sum.get("surface_pressure_avg_hpa")),
            "weather_description": desc,
            "icon_url": primary.get("icon_url"),
            "full_icon_url": primary.get("full_icon_url"),
            "wind": {
                "speed_ms": observed("windspeed_ms", wind_fld.get("mean_speed_ms")),
                "speed_kmh": observed("windspeed_kmh", wind_fld.get("mean_speed_kmh")),
                "bft": wind_bft,
                "gusts_ms": observed("windgusts_ms", round(wind_fld.get("max_gusts_kmh", 0) / 3.6, 1)),
                "gusts_kmh": observed("windgusts_kmh", wind_fld.get("max_gusts_kmh")),
                "direction": wind_dir if wind_dir != "—" else wind_fld.get("direction_compass", "ZW"),
                "degrees": observed("winddirectiondegrees", wind_fld.get("mean_direction_deg")),
                "u_ms": wind_fld.get("mean_u_ms", 3.4),
                "v_ms": wind_fld.get("mean_v_ms", 2.9),
            },
            "precipitation": {
                "current_mm_h": observed("precipitation_mm_h", city_sum.get("precipitation_avg_mm_h") or 0.0),
                "nowcast_status": rain_nowcast.get("status", "unavailable"),
                "currently_raining": is_raining or (city_sum.get("precipitation_max_mm_h", 0.0) > 0.05),
                "will_rain_in_2h": rain_will_rain,
                "first_rain_in_minutes": rain_minutes,
                "max_expected_mm_h": max(rain_max, city_sum.get("precipitation_max_mm_h", 0.0)),
                "rainfall_last_hour": observed("rainfall_last_hour", 0.0),
            },
            "summary": summary,
            "stations": stations_summary,
            "radar_latest_tile_url": latest_radar_url,
            "total_nodes": spatial_grid.get("total_nodes", 12),
            "features": spatial_grid.get("features", []),
            "grid_nodes": spatial_grid.get("grid_nodes", []),
            "city_summary": spatial_grid.get("city_summary"),
            "wind_field": spatial_grid.get("wind_field"),
            "solar": spatial_grid.get("solar"),
            "storm_flags": spatial_grid.get("storm_flags"),
        }

        # Cache in Redis with 120-second TTL for sub-5ms delivery
        await set_cached_json("weather:live:rotterdam", overview, ttl_seconds=120)
        await set_cached_json("weather:live:last_good", overview, ttl_seconds=86400)
        return overview

    # =========================================================================
    # 3. 12-POINT ROTTERDAM SPATIAL WEATHER MICRO-GRID (KNMI HARMONIE AROME)
    # =========================================================================
    def _build_grid_node_payload(
        self,
        node_meta: Dict[str, Any],
        current: Dict[str, Any],
        now_iso: str,
        solar_is_day: int,
    ) -> Dict[str, Any]:
        """Normalize raw Open-Meteo / KNMI HARMONIE node readings into shader-ready telemetry."""
        required = OPEN_METEO_CURRENT_FIELDS.split(",")
        if not current.get("time") or any(
            not isinstance(current.get(key), (int, float)) or not math.isfinite(current[key])
            for key in required
        ):
            raise ValueError("Incomplete upstream weather data")
        interval = current.get("interval")
        if not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval <= 0:
            raise ValueError("Missing precipitation accumulation interval")

        def val(key: str, default_val: Any = None) -> Any:
            value = current[key]
            return value * 3600.0 / interval if key in ("precipitation", "rain", "showers", "snowfall") else value

        cloud_cover = float(max(0.0, min(100.0, val("cloud_cover", 45.0))))
        cloud_low = float(max(0.0, min(100.0, val("cloud_cover_low", cloud_cover * 0.6))))
        cloud_mid = float(max(0.0, min(100.0, val("cloud_cover_mid", cloud_cover * 0.4))))
        cloud_high = float(max(0.0, min(100.0, val("cloud_cover_high", cloud_cover * 0.2))))

        rain = float(max(0.0, val("rain", 0.0)))
        showers = float(max(0.0, val("showers", 0.0)))
        snowfall = float(max(0.0, val("snowfall", 0.0)))
        precip = float(max(0.0, val("precipitation", rain + showers)))

        w_code = int(val("weather_code", 2))
        w_desc = wmo_weather_description_nl(w_code)

        wind_kmh = float(max(0.0, val("wind_speed_10m", 16.0)))
        wind_ms = round(wind_kmh / 3.6, 2)
        wind_deg = int(round(float(val("wind_direction_10m", 235)))) % 360
        gusts_kmh = float(max(wind_kmh, val("wind_gusts_10m", wind_kmh * 1.35)))
        gusts_ms = round(gusts_kmh / 3.6, 2)

        # Meteorological wind direction is where wind blows FROM; advection vector (u, v) is where air moves TO
        rad_from = math.radians(wind_deg)
        wind_u = round(-wind_ms * math.sin(rad_from), 3)
        wind_v = round(-wind_ms * math.cos(rad_from), 3)

        temp_2m = round(float(val("temperature_2m", 16.0)), 1)
        app_temp = round(float(val("apparent_temperature", temp_2m)), 1)
        humidity = round(float(max(0.0, min(100.0, val("relative_humidity_2m", 78.0)))), 1)
        visibility = round(float(max(50.0, val("visibility", 30000.0))), 1)
        pressure = round(float(val("surface_pressure", 1016.0)), 1)
        cape = round(float(max(0.0, val("cape", 20.0))), 1)
        is_day = int(val("is_day", solar_is_day))

        # Compute normalized WebGL shader storm intensity [0.0..1.0]
        precip_factor = min(1.0, precip / 6.0)
        gust_factor = max(0.0, min(1.0, (gusts_kmh - 38.0) / 52.0))
        cape_factor = min(1.0, cape / 1200.0)
        code_storm = 1.0 if w_code in (95, 96, 99) else (0.65 if w_code in (65, 82) else 0.0)
        storm_intensity = round(
            min(1.0, max(code_storm, precip_factor * 0.75 + gust_factor * 0.25, cape_factor * 0.8)),
            3,
        )

        # Compute normalized WebGL shader fog/mist density [0.0..1.0]
        vis_fog = max(0.0, min(1.0, (4500.0 - visibility) / 4000.0)) if visibility < 4500.0 else 0.0
        code_fog = 0.85 if w_code in (45, 48) else 0.0
        zone_boost = 1.15 if node_meta["zone"] in ("coastal", "harbor", "river") else 1.0
        fog_density = round(min(1.0, max(code_fog, vis_fog * zone_boost)), 3)



        return {
            "node_id": node_meta["node_id"],
            "node_index": node_meta["node_index"],
            "id": node_meta["id"],
            "name": node_meta["name"],
            "district": node_meta["district"],
            "zone": node_meta["zone"],
            "lat": node_meta["lat"],
            "lon": node_meta["lon"],
            "timestamp": datetime.fromisoformat(current["time"]).replace(tzinfo=timezone.utc).isoformat(),
            "cloud_cover": cloud_cover,
            "cloud_cover_low": cloud_low,
            "cloud_cover_mid": cloud_mid,
            "cloud_cover_high": cloud_high,
            "precipitation": round(precip, 2),
            "rain": round(rain, 2),
            "showers": round(showers, 2),
            "snowfall": round(snowfall, 2),
            "weather_code": w_code,
            "weather_description": w_desc,
            "wind_speed_10m": round(wind_kmh, 1),
            "wind_speed_ms": wind_ms,
            "wind_direction_10m": wind_deg,
            "wind_gusts_10m": round(gusts_kmh, 1),
            "wind_gusts_ms": gusts_ms,
            "wind_u": wind_u,
            "wind_v": wind_v,
            "temperature_2m": temp_2m,
            "apparent_temperature": app_temp,
            "relative_humidity_2m": humidity,
            "visibility": visibility,
            "surface_pressure": pressure,
            "cape": cape,
            "is_day": is_day,
            "storm_intensity": storm_intensity,
            "fog_density": fog_density,
            "lightning_active": False,
        }

    async def fetch_spatial_weather_grid(
        self, sync_live_overview: bool = True
    ) -> Dict[str, Any]:
        """
        Poll and cache real-time meteorological telemetry across the 12-node spatial mesh
        spanning Rotterdam Island using Open-Meteo KNMI HARMONIE AROME (2km high-res model).
        Cached in Redis under 'weather:spatial:grid' with a 120s TTL (<5ms SLA).
        """
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        solar = calculate_solar_position(now, ROTTERDAM_SOLAR_LAT, ROTTERDAM_SOLAR_LON)

        lats_str = ",".join(str(n["lat"]) for n in ROTTERDAM_WEATHER_GRID_NODES)
        lons_str = ",".join(str(n["lon"]) for n in ROTTERDAM_WEATHER_GRID_NODES)

        client = await self.get_client()
        raw_nodes_list: List[Dict[str, Any]] = []

        try:
            resp = await client.get(
                OPEN_METEO_KNMI_URL,
                params={
                    "latitude": lats_str,
                    "longitude": lons_str,
                    "current": OPEN_METEO_CURRENT_FIELDS,
                    "models": "knmi_seamless",
                },
                headers={"User-Agent": "RotterdamLive/2.2"},
            )
            if resp.status_code == 200:
                payload = resp.json()
                if isinstance(payload, list) and len(payload) == len(ROTTERDAM_WEATHER_GRID_NODES):
                    raw_nodes_list = [item.get("current", {}) or {} for item in payload]
                elif isinstance(payload, dict) and "current" in payload:
                    raw_nodes_list = [payload.get("current", {}) or {}]
            else:
                logger.warning("Open-Meteo KNMI grid query returned status {}", resp.status_code)
        except Exception as e:
            logger.warning("Open-Meteo KNMI 12-node grid query failed, retaining last successful snapshot: {}", e)

        try:
            if len(raw_nodes_list) != 12:
                raise ValueError("Incomplete spatial grid")
            for node, current in zip(ROTTERDAM_WEATHER_GRID_NODES, raw_nodes_list):
                self._build_grid_node_payload(node, current, now_iso, solar["is_day"])
        except (ValueError, TypeError):
            previous = await get_cached_json("weather:spatial:last_good")
            if previous:
                return {**previous, "data_status": "stale"}
            raise ValueError("Weather provider unavailable and no previous observations exist")

        features: List[Dict[str, Any]] = []
        grid_nodes: List[Dict[str, Any]] = []

        for idx, node_meta in enumerate(ROTTERDAM_WEATHER_GRID_NODES):
            raw_cur = raw_nodes_list[idx] if idx < len(raw_nodes_list) else {}
            props = self._build_grid_node_payload(node_meta, raw_cur, now_iso, solar["is_day"])
            grid_nodes.append(props)
            features.append({
                "type": "Feature",
                "id": node_meta["id"],
                "geometry": {
                    "type": "Point",
                    "coordinates": [node_meta["lon"], node_meta["lat"]],
                },
                "properties": props,
            })

        n_count = len(grid_nodes)
        temps = [n["temperature_2m"] for n in grid_nodes]
        clouds = [n["cloud_cover"] for n in grid_nodes]
        clouds_low = [n["cloud_cover_low"] for n in grid_nodes]
        clouds_mid = [n["cloud_cover_mid"] for n in grid_nodes]
        clouds_high = [n["cloud_cover_high"] for n in grid_nodes]
        precips = [n["precipitation"] for n in grid_nodes]
        humidities = [n["relative_humidity_2m"] for n in grid_nodes]
        visibilities = [n["visibility"] for n in grid_nodes]
        pressures = [n["surface_pressure"] for n in grid_nodes]
        capes = [n["cape"] for n in grid_nodes]
        gusts = [n["wind_gusts_10m"] for n in grid_nodes]
        speeds_kmh = [n["wind_speed_10m"] for n in grid_nodes]
        speeds_ms = [n["wind_speed_ms"] for n in grid_nodes]
        u_vals = [n["wind_u"] for n in grid_nodes]
        v_vals = [n["wind_v"] for n in grid_nodes]

        dominant_code = max((n["weather_code"] for n in grid_nodes), default=2)
        city_summary = {
            "temperature_avg_c": round(sum(temps) / n_count, 1),
            "temperature_min_c": round(min(temps), 1),
            "temperature_max_c": round(max(temps), 1),
            "cloud_cover_avg_pct": round(sum(clouds) / n_count, 1),
            "cloud_cover_low_avg_pct": round(sum(clouds_low) / n_count, 1),
            "cloud_cover_mid_avg_pct": round(sum(clouds_mid) / n_count, 1),
            "cloud_cover_high_avg_pct": round(sum(clouds_high) / n_count, 1),
            "precipitation_avg_mm_h": round(sum(precips) / n_count, 2),
            "precipitation_max_mm_h": round(max(precips), 2),
            "humidity_avg_pct": round(sum(humidities) / n_count, 1),
            "visibility_min_m": round(min(visibilities), 1),
            "surface_pressure_avg_hpa": round(sum(pressures) / n_count, 1),
            "dominant_weather_code": dominant_code,
            "dominant_weather_description": wmo_weather_description_nl(dominant_code),
        }

        mean_u = round(sum(u_vals) / n_count, 3)
        mean_v = round(sum(v_vals) / n_count, 3)
        # Convert mean advection vector back to meteorological "from" direction degrees
        if abs(mean_u) > 1e-4 or abs(mean_v) > 1e-4:
            mean_dir_deg = int(round((math.degrees(math.atan2(-mean_u, -mean_v)) + 360.0) % 360.0))
        else:
            mean_dir_deg = int(round(sum(n["wind_direction_10m"] for n in grid_nodes) / n_count)) % 360

        coastal_nodes = [n for n in grid_nodes if n["zone"] == "coastal"]
        inland_nodes = [n for n in grid_nodes if n["zone"] in ("urban", "inland")]
        coastal_spd = round(
            sum(n["wind_speed_10m"] for n in coastal_nodes) / max(1, len(coastal_nodes)), 1
        )
        inland_spd = round(
            sum(n["wind_speed_10m"] for n in inland_nodes) / max(1, len(inland_nodes)), 1
        )

        wind_field = {
            "mean_speed_kmh": round(sum(speeds_kmh) / n_count, 1),
            "mean_speed_ms": round(sum(speeds_ms) / n_count, 2),
            "max_gusts_kmh": round(max(gusts), 1),
            "mean_direction_deg": mean_dir_deg,
            "direction_compass": degrees_to_compass_nl(mean_dir_deg),
            "mean_u_ms": mean_u,
            "mean_v_ms": mean_v,
            "coastal_speed_kmh": coastal_spd,
            "inland_speed_kmh": inland_spd,
            "coastal_inland_gradient_kmh": round(coastal_spd - inland_spd, 1),
        }

        max_precip = max(precips)
        max_gusts = max(gusts)
        max_cape = max(capes)
        is_thunder = any(n["weather_code"] in (95, 96, 99) for n in grid_nodes)
        is_storm = bool(
            is_thunder
            or max_precip >= 4.0
            or max_gusts >= 60.0
            or dominant_code in (65, 82, 95, 96, 99)
        )
        coastal_squall = bool(
            any(n["precipitation"] >= 1.5 or n["wind_gusts_10m"] >= 50.0 for n in coastal_nodes)
        )
        storm_flags = {
            "is_storm": is_storm,
            "is_thunderstorm": is_thunder,
            "lightning_probability": None,
            "coastal_squall": coastal_squall,
            "fog_advisory": min(visibilities) < 3000.0,
            "active_rain_nodes": sum(1 for n in grid_nodes if n["precipitation"] > 0.05),
            "max_cape_j_kg": round(max_cape, 1),
            "max_precipitation_mm_h": round(max_precip, 2),
            "max_wind_gusts_kmh": round(max_gusts, 1),
        }

        grid_response = {
            "type": "FeatureCollection",
            "generated_at": now_iso,
            "data_status": "fresh" if all(-300 <= (now - datetime.fromisoformat(n["timestamp"])).total_seconds() <= 1800 for n in grid_nodes) else "stale",
            "source": "Open-Meteo / KNMI HARMONIE model",
            "ttl_seconds": 120,
            "model": "knmi_harmonie_arome",
            "total_nodes": n_count,
            "features": features,
            "grid_nodes": grid_nodes,
            "city_summary": city_summary,
            "wind_field": wind_field,
            "solar": solar,
            "storm_flags": storm_flags,
        }

        # Cache in Redis with 120s TTL (<5ms SLA)
        await set_cached_json("weather:spatial:grid", grid_response, ttl_seconds=120)
        await set_cached_json("weather:spatial:last_good", grid_response, ttl_seconds=86400)

        if sync_live_overview:
            existing_stations_fc = await get_cached_json("weather:stations:all")
            st_features = existing_stations_fc.get("features", []) if existing_stations_fc else []
            primary_st = next(
                (f["properties"] for f in st_features if f.get("properties", {}).get("is_primary")),
                None,
            )
            await self._build_and_cache_live_overview(primary_st, st_features)

        return grid_response

    # =========================================================================
    # 4. ANIMATED RADAR TILE FEED FOR MAPLIBRE (RAINVIEWER)
    # =========================================================================
    async def fetch_radar_frames(self) -> Dict[str, Any]:
        """
        Fetch RainViewer radar frames timeline and generate MapLibre tile URL templates.
        Allows Svelte frontend to render smooth animated rain radar overlays.
        """
        cache_key = "weather:radar:frames"
        client = await self.get_client()

        try:
            resp = await client.get(
                RAINVIEWER_RADAR_URL,
                headers={"User-Agent": "RotterdamLive/1.5"},
            )
            if resp.status_code == 200:
                data = resp.json()
            else:
                logger.warning("RainViewer API returned status {}", resp.status_code)
                data = {}
        except Exception as e:
            logger.warning("Failed fetching RainViewer radar timeline: {}", e)
            data = {}

        host = data.get("host", "https://tilecache.rainviewer.com")
        generated = data.get("generated", int(datetime.now(timezone.utc).timestamp()))
        radar = data.get("radar", {})

        raw_past = radar.get("past", [])
        raw_nowcast = radar.get("nowcast", [])

        # Generic MapLibre tile URL template
        tile_template = f"{host}/v2/radar/{{path}}/512/{{z}}/{{x}}/{{y}}/2/1_1.png"

        past_frames: List[Dict[str, Any]] = []
        for f in raw_past:
            path = f.get("path", "")
            t = f.get("time", 0)
            formatted = datetime.fromtimestamp(t, tz=timezone.utc).isoformat()
            tile_url = f"{host}{path}/512/{{z}}/{{x}}/{{y}}/2/1_1.png"
            past_frames.append({
                "time": t,
                "formatted_time": formatted,
                "path": path,
                "tile_url": tile_url,
            })

        nowcast_frames: List[Dict[str, Any]] = []
        for f in raw_nowcast:
            path = f.get("path", "")
            t = f.get("time", 0)
            formatted = datetime.fromtimestamp(t, tz=timezone.utc).isoformat()
            tile_url = f"{host}{path}/512/{{z}}/{{x}}/{{y}}/2/1_1.png"
            nowcast_frames.append({
                "time": t,
                "formatted_time": formatted,
                "path": path,
                "tile_url": tile_url,
            })

        latest_frame = past_frames[-1] if past_frames else None

        response_data = {
            "host": host,
            "generated": generated,
            "tile_size": 512,
            "tile_url_template": tile_template,
            "color_scheme": 2,
            "smooth": 1,
            "snow": 1,
            "past_frames": past_frames,
            "nowcast_frames": nowcast_frames,
            "latest_frame": latest_frame,
        }

        # Cache in Redis with 5-minute TTL
        await set_cached_json(cache_key, response_data, ttl_seconds=300)
        return response_data
