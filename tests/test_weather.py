"""Tests for Live Weather, Precipitation Nowcast & Rain Radar API endpoints."""
import pytest
import httpx
from app.main import app
from app.ingestion.weather_harvester import raw_rain_to_mm_h


def test_raw_rain_to_mm_h_formula():
    """Verify standard Buienradar mathematical formula conversion."""
    # Zero value is exactly 0.0 mm/h
    assert raw_rain_to_mm_h("000") == 0.0
    assert raw_rain_to_mm_h("0") == 0.0
    assert raw_rain_to_mm_h("-1") == 0.0
    assert raw_rain_to_mm_h("invalid") == 0.0

    # 77 raw value -> 10^((77 - 109)/32) = 10^(-1) = 0.1 mm/h
    assert raw_rain_to_mm_h("077") == 0.10

    # 109 raw value -> 10^0 = 1.0 mm/h
    assert raw_rain_to_mm_h("109") == 1.00

    # 141 raw value -> 10^1 = 10.0 mm/h
    assert raw_rain_to_mm_h("141") == 10.00


@pytest.mark.asyncio
async def test_live_weather_endpoint():
    """Verify GET /api/v1/weather/live returns unified instant overview."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/weather/live")
        assert resp.status_code == 200
        data = resp.json()

        assert data["location"] == "Rotterdam"
        assert "station_id" in data
        assert "station_name" in data
        assert "weather_description" in data
        assert "summary" in data
        assert "wind" in data
        assert "precipitation" in data
        assert "stations" in data

        wind = data["wind"]
        assert "speed_kmh" in wind
        assert "bft" in wind
        assert "direction" in wind

        precip = data["precipitation"]
        assert "currently_raining" in precip
        assert "will_rain_in_2h" in precip


@pytest.mark.asyncio
async def test_rain_forecast_endpoint():
    """Verify GET /api/v1/weather/rain-forecast returns 2-hour timeline."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/weather/rain-forecast?lat=51.9244&lon=4.4777")
        assert resp.status_code == 200
        data = resp.json()

        assert "location" in data
        assert "generated_at" in data
        assert "will_rain_in_2h" in data
        assert "max_intensity_mm_h" in data
        assert "summary" in data
        assert "timeline" in data

        timeline = data["timeline"]
        assert len(timeline) >= 20
        first_item = timeline[0]
        assert "time" in first_item
        assert "intensity_mm_h" in first_item
        assert "raw_value" in first_item


@pytest.mark.asyncio
async def test_weather_radar_endpoint():
    """Verify GET /api/v1/weather/radar returns MapLibre tile stream."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/weather/radar")
        assert resp.status_code == 200
        data = resp.json()

        assert "host" in data
        assert "tile_url_template" in data
        assert "{z}/{x}/{y}" in data["tile_url_template"]
        assert "past_frames" in data
        assert "latest_frame" in data

        if data["past_frames"]:
            frame = data["past_frames"][0]
            assert "time" in frame
            assert "path" in frame
            assert "tile_url" in frame
            assert "{z}/{x}/{y}" in frame["tile_url"]


@pytest.mark.asyncio
async def test_weather_stations_endpoint():
    """Verify GET /api/v1/weather/stations returns official KNMI stations FeatureCollection."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/weather/stations")
        assert resp.status_code == 200
        data = resp.json()

        assert data["type"] == "FeatureCollection"
        assert "features" in data
        assert data["total_stations"] >= 3

        station_ids = [f["properties"]["station_id"] for f in data["features"]]
        assert 6344 in station_ids  # Rotterdam Airport Zestienhoven
        assert 6330 in station_ids  # Hoek van Holland
        assert 6343 in station_ids  # Rotterdam Geulhaven

        # Check primary station structure
        primary = next(f for f in data["features"] if f["properties"]["station_id"] == 6344)
        assert primary["properties"]["is_primary"] is True
        assert primary["geometry"]["type"] == "Point"
        assert len(primary["geometry"]["coordinates"]) == 2


@pytest.mark.asyncio
async def test_weather_station_by_id():
    """Verify GET /api/v1/weather/stations/{station_id} for Rotterdam Airport."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/weather/stations/6344")
        assert resp.status_code == 200
        data = resp.json()

        assert data["type"] == "Feature"
        props = data["properties"]
        assert props["station_id"] == 6344
        assert props["is_primary"] is True
        assert "temperature" in props
        assert "windspeed_kmh" in props


@pytest.mark.asyncio
async def test_weather_station_not_found():
    """Verify GET /api/v1/weather/stations/999999 returns 404."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/weather/stations/999999")
        assert resp.status_code == 404
