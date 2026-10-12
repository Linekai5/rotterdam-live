"""Environment, Weather & Air Quality Ingestor (Open-Meteo & DCMR/Luchtmeetnet)."""
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from app.ingestion.base import BaseIngestor
from app.logging import logger
from app.services.spatial_service import find_district_for_point, upsert_live_event
from app.db.session import AsyncSessionLocal
from app.config import settings

OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast?"
    "latitude=51.9244&longitude=4.4777&"
    "current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,weather_code,wind_speed_10m,wind_gusts_10m"
)

# Known active DCMR air quality stations in Rotterdam region
DCMR_ROTTERDAM_STATIONS = [
    {
        "number": "NL01485",
        "name": "Rotterdam-Hoogvliet",
        "lon": 4.3552,
        "lat": 51.8674,
        "district": "Hoogvliet",
    },
    {
        "number": "NL01487",
        "name": "Rotterdam-Pleinweg",
        "lon": 4.4842,
        "lat": 51.8951,
        "district": "Charlois",
    },
    {
        "number": "NL01489",
        "name": "Rotterdam-Schiedamse Vest",
        "lon": 4.4815,
        "lat": 51.9167,
        "district": "Centrum",
    },
    {
        "number": "NL01491",
        "name": "Rotterdam-Maashaven",
        "lon": 4.4920,
        "lat": 51.9010,
        "district": "Feijenoord",
    },
    {
        "number": "NL01494",
        "name": "Rotterdam-Botlek",
        "lon": 4.3150,
        "lat": 51.8750,
        "district": "Botlek",
    },
]


def wmo_weather_description(code: int) -> str:
    """Map WMO weather code to clear human-readable Dutch description."""
    codes = {
        0: "Helder",
        1: "Overwegend helder",
        2: "Licht bewolkt",
        3: "Geheel bewolkt",
        45: "Mist",
        48: "Aanvriezende mist",
        51: "Lichte motregen",
        53: "Matige motregen",
        55: "Dichte motregen",
        61: "Lichte regen",
        63: "Matige regen",
        65: "Zware regen",
        71: "Lichte sneeuwval",
        73: "Matige sneeuwval",
        75: "Zware sneeuwval",
        80: "Lichte regenbui",
        81: "Matige regenbui",
        82: "Hevige regenbui",
        95: "Onweer",
        96: "Onweer met lichte hagel",
        99: "Zwaar onweer met hagel",
    }
    return codes.get(code, "Wisselvallig")


class EnvironmentIngestor(BaseIngestor):
    def __init__(self):
        super().__init__(name="environment_unified", timeout_seconds=20.0)

    async def ingest(self) -> Dict[str, Any]:
        """Ingest Open-Meteo weather and DCMR air quality measurements."""
        weather_saved = await self._ingest_weather()
        air_saved = await self._ingest_air_quality()
        return {"weather_records": weather_saved, "air_quality_stations": air_saved}

    async def _ingest_weather(self) -> int:
        """Fetch current weather metrics from Open-Meteo."""
        client = await self.get_client()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=30)
        saved = 0

        try:
            resp = await client.get(OPEN_METEO_URL)
            if resp.status_code == 200:
                data = resp.json()
                current = data.get("current", {})

                temp = current.get("temperature_2m", 0.0)
                apparent_temp = current.get("apparent_temperature", temp)
                humidity = current.get("relative_humidity_2m", 0)
                precipitation = current.get("precipitation", 0.0)
                weather_code = current.get("weather_code", 0)
                wind_speed = current.get("wind_speed_10m", 0.0)
                wind_gusts = current.get("wind_gusts_10m", 0.0)

                condition_nl = wmo_weather_description(weather_code)

                # Severity logic based on gusts and precipitation
                severity = 1
                if wind_gusts > 75.0 or precipitation > 10.0:
                    severity = 4
                elif wind_gusts > 50.0 or precipitation > 3.0:
                    severity = 2

                title = f"Weer Rotterdam: {temp}°C, {condition_nl}"

                event_data = {
                    "id": "weather-rotterdam-current",
                    "category": "environment",
                    "subcategory": "weather",
                    "severity": severity,
                    "timestamp": now,
                    "expires_at": expires_at,
                    "district": "Rotterdam Centrum",
                    "title": title,
                    "details": {
                        "temperature": temp,
                        "apparent_temperature": apparent_temp,
                        "humidity": humidity,
                        "precipitation_mm": precipitation,
                        "wind_speed_kmh": wind_speed,
                        "wind_gusts_kmh": wind_gusts,
                        "weather_code": weather_code,
                        "condition": condition_nl,
                        "source": "Open-Meteo",
                    },
                    "lon": settings.ROTTERDAM_CENTER_LON,
                    "lat": settings.ROTTERDAM_CENTER_LAT,
                }

                async with AsyncSessionLocal() as session:
                    if await upsert_live_event(event_data, session):
                        saved += 1
        except Exception as e:
            logger.warning("Failed fetching Open-Meteo weather: {}", e)
        return saved

    async def _ingest_air_quality(self) -> int:
        """Fetch real-time air quality metrics from Luchtmeetnet DCMR stations."""
        client = await self.get_client()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=1)
        saved = 0

        async with AsyncSessionLocal() as session:
            for st in DCMR_ROTTERDAM_STATIONS:
                url = f"https://api.luchtmeetnet.nl/open_api/stations/{st['number']}/measurements"
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json().get("data", [])

                        measurements = {}
                        for m in data[:15]:
                            formula = m.get("formula")
                            if formula and formula not in measurements:
                                measurements[formula] = {
                                    "value": m.get("value"),
                                    "timestamp": m.get("timestamp_measured"),
                                }

                        pm25 = measurements.get("PM25", {}).get("value", 0.0) or 0.0
                        pm10 = measurements.get("PM10", {}).get("value", 0.0) or 0.0
                        no2 = measurements.get("NO2", {}).get("value", 0.0) or 0.0

                        # Calculate European CAQI air index (1=Good, 2=Moderate, 3=Unhealthy, 4=Very Unhealthy)
                        severity = 1
                        if pm25 > 50 or no2 > 100 or pm10 > 90:
                            severity = 4
                        elif pm25 > 25 or no2 > 50 or pm10 > 50:
                            severity = 3
                        elif pm25 > 15 or no2 > 30 or pm10 > 30:
                            severity = 2

                        aqi_label = {1: "Goed", 2: "Matig", 3: "Onvoldoende", 4: "Slecht"}.get(
                            severity, "Normaal"
                        )

                        event_id = f"airquality-{st['number']}"
                        event_data = {
                            "id": event_id,
                            "category": "environment",
                            "subcategory": "air_quality",
                            "severity": severity,
                            "timestamp": now,
                            "expires_at": expires_at,
                            "district": st.get("district"),
                            "title": f"Luchtkwaliteit {st['name']}: {aqi_label}",
                            "details": {
                                "station_number": st["number"],
                                "station_name": st["name"],
                                "air_quality_index": severity,
                                "air_quality_label": aqi_label,
                                "pm25": pm25,
                                "pm10": pm10,
                                "no2": no2,
                                "measurements": measurements,
                                "organisation": "DCMR Milieudienst Rijnmond",
                            },
                            "lon": st["lon"],
                            "lat": st["lat"],
                        }
                        if await upsert_live_event(event_data, session):
                            saved += 1
                except Exception as e:
                    logger.debug("Failed ingesting air quality for station {}: {}", st["number"], e)
        return saved
