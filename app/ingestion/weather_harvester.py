"""Hyper-Accurate Live Weather, Precipitation Nowcast & Rain Radar Harvester.

Data Sources:
1. Buienradar 2-hour Rain Nowcast (gpsgadget.buienradar.nl)
2. Buienradar & KNMI Official Observation Stations (data.buienradar.nl/2.0/feed/json)
3. RainViewer Open Radar API (api.rainviewer.com)
"""
import math
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
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
    """Orchestrates hyper-local weather nowcasts, KNMI telemetry & radar tile streams."""

    def __init__(self):
        super().__init__(name="rotterdam_weather_harvester", timeout_seconds=15.0)

    async def ingest(self) -> Dict[str, Any]:
        """Run all weather harvesting tasks and refresh databases & Redis caches."""
        rain_result = await self.fetch_rain_nowcast()
        stations_result = await self.fetch_weather_stations()
        radar_result = await self.fetch_radar_frames()

        return {
            "rain_nowcast_generated": rain_result.get("generated_at"),
            "stations_count": stations_result.get("total_stations", 0),
            "radar_past_frames": len(radar_result.get("past_frames", [])),
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
                            raw_val = int(val_str) if val_str.isdigit() else 0
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

        # Fallback if Buienradar is unreachable: 24 empty 5-min intervals
        now = datetime.now(timezone.utc)
        if not timeline:
            logger.info("Using empty nowcast fallback for weather:rain")
            for i in range(24):
                slot_time = (now + timedelta(minutes=i * 5)).strftime("%H:%M")
                timeline.append({
                    "time": slot_time,
                    "intensity_mm_h": 0.0,
                    "raw_value": 0,
                })

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
                    first_rain_in_minutes = idx * 5
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
            "will_rain_in_2h": will_rain_in_2h,
            "max_intensity_mm_h": max_intensity,
            "first_rain_in_minutes": first_rain_in_minutes,
            "summary": summary,
            "timeline": timeline,
        }

        # Cache in Redis with 5-minute TTL (300 seconds)
        await set_cached_json(cache_key, response_data, ttl_seconds=300)
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
                    "timestamp": s.get("timestamp", now.isoformat()),
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

        temp = primary.get("temperature")
        feel_temp = primary.get("feeltemperature")
        desc = primary.get("weather_description") or "Bewolkt"
        wind_bft = primary.get("windspeed_bft") or 3
        wind_dir = primary.get("winddirection") or "—"
        wind_kmh = primary.get("windspeed_kmh") or 15.0

        rain_will_rain = rain_nowcast.get("will_rain_in_2h", False)
        rain_minutes = rain_nowcast.get("first_rain_in_minutes")
        rain_max = rain_nowcast.get("max_intensity_mm_h", 0.0)
        is_raining = rain_nowcast.get("timeline", [{}])[0].get("intensity_mm_h", 0.0) > 0

        # Construct live summary sentence
        if is_raining:
            summary = f"{desc} in Rotterdam ({temp}°C), regenachtig ({rain_nowcast['timeline'][0]['intensity_mm_h']} mm/u)"
        elif rain_will_rain and rain_minutes is not None:
            summary = f"{desc} in Rotterdam ({temp}°C), droog komende {rain_minutes} minuten, daarna regen ({rain_max} mm/u)"
        else:
            summary = f"{desc} in Rotterdam ({temp}°C), droog komende 2 uur met matige wind ({wind_bft} Bft {wind_dir})"

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
        latest_radar_url = radar_data.get("latest_frame", {}).get("tile_url") if radar_data else None

        overview = {
            "generated_at": now.isoformat(),
            "location": "Rotterdam",
            "station_name": primary.get("station_name", "Rotterdam Airport"),
            "station_id": primary.get("station_id", 6344),
            "temperature": temp,
            "feeltemperature": feel_temp,
            "humidity": primary.get("humidity"),
            "airpressure": primary.get("airpressure"),
            "weather_description": desc,
            "icon_url": primary.get("icon_url"),
            "full_icon_url": primary.get("full_icon_url"),
            "wind": {
                "speed_ms": primary.get("windspeed_ms"),
                "speed_kmh": wind_kmh,
                "bft": wind_bft,
                "gusts_ms": primary.get("windgusts_ms"),
                "gusts_kmh": primary.get("windgusts_kmh"),
                "direction": wind_dir,
                "degrees": primary.get("winddirectiondegrees"),
            },
            "precipitation": {
                "current_mm_h": primary.get("precipitation_mm_h") or 0.0,
                "currently_raining": is_raining,
                "will_rain_in_2h": rain_will_rain,
                "first_rain_in_minutes": rain_minutes,
                "max_expected_mm_h": rain_max,
                "rainfall_last_hour": primary.get("rainfall_last_hour") or 0.0,
            },
            "summary": summary,
            "stations": stations_summary,
            "radar_latest_tile_url": latest_radar_url,
        }

        # Cache in Redis with 5-minute TTL
        await set_cached_json("weather:live:rotterdam", overview, ttl_seconds=300)
        return overview

    # =========================================================================
    # 3. ANIMATED RADAR TILE FEED FOR MAPLIBRE (RAINVIEWER)
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

        latest_frame = past_frames[-1] if past_frames else (nowcast_frames[0] if nowcast_frames else None)

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
