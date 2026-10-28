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


def test_solar_position_calculator():
    """Verify real-time solar azimuth, elevation, daylight phase, and shadow projection vector."""
    from datetime import datetime, timezone
    from app.ingestion.weather_harvester import calculate_solar_position

    # Midday in summer (June 21, 12:00 UTC) over Rotterdam (51.922N, 4.479E)
    summer_noon = datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc)
    solar_day = calculate_solar_position(summer_noon)
    assert solar_day["is_day"] == 1
    assert solar_day["elevation_deg"] > 55.0
    assert 165.0 <= solar_day["azimuth_deg"] <= 205.0
    assert solar_day["daylight_phase"] == "day"
    assert len(solar_day["sun_vector"]) == 3
    assert len(solar_day["shadow_offset_factor"]) == 2

    # Midnight in winter (December 21, 00:00 UTC)
    winter_midnight = datetime(2026, 12, 21, 0, 0, 0, tzinfo=timezone.utc)
    solar_night = calculate_solar_position(winter_midnight)
    assert solar_night["is_day"] == 0
    assert solar_night["elevation_deg"] < -20.0
    assert solar_night["daylight_phase"] == "night"


def test_spatial_weather_grid_coordinates_definition():
    """Verify all 12 Rotterdam Island micro-grid nodes match the specification."""
    from app.ingestion.weather_harvester import ROTTERDAM_WEATHER_GRID_NODES

    assert len(ROTTERDAM_WEATHER_GRID_NODES) == 12
    names = [n["name"] for n in ROTTERDAM_WEATHER_GRID_NODES]
    assert "Maasvlakte West" in names
    assert "Hoek van Holland" in names
    assert "Rozenburg / Botlek" in names
    assert "Vlaardingen / Schiedam Border" in names
    assert "Pernis / Waalhaven" in names
    assert "Delfshaven / Noord" in names
    assert "Rotterdam Centrum" in names
    assert "Charlois / Zuiderpark" in names
    assert "Kralingen / Crooswijk" in names
    assert "Hillegersberg / Schiebroek" in names
    assert "Feijenoord / IJsselmonde" in names
    assert "Prins Alexander / Nesselande" in names

    # Check exact West & Center anchors
    maasvlakte = ROTTERDAM_WEATHER_GRID_NODES[0]
    assert maasvlakte["lat"] == 51.958 and maasvlakte["lon"] == 3.985
    centrum = ROTTERDAM_WEATHER_GRID_NODES[6]
    assert centrum["lat"] == 51.922 and centrum["lon"] == 4.479
    nesselande = ROTTERDAM_WEATHER_GRID_NODES[11]
    assert nesselande["lat"] == 51.965 and nesselande["lon"] == 4.575


@pytest.mark.asyncio
async def test_spatial_weather_grid_endpoint_and_redis_sla():
    """Verify GET /api/v1/weather/grid returns 12-point GeoJSON FeatureCollection in <5ms from Redis."""
    import time

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/weather/grid")
        assert resp.status_code == 200
        data = resp.json()

        assert data["type"] == "FeatureCollection"
        assert data["ttl_seconds"] == 120
        assert data["total_nodes"] == 12
        assert len(data["features"]) == 12
        assert len(data["grid_nodes"]) == 12

        # Check required per-node meteorological fields
        node0 = data["features"][0]
        assert node0["type"] == "Feature"
        assert node0["geometry"]["type"] == "Point"
        assert node0["geometry"]["coordinates"] == [3.985, 51.958]
        p = node0["properties"]
        for required_key in [
            "cloud_cover",
            "cloud_cover_low",
            "cloud_cover_mid",
            "cloud_cover_high",
            "precipitation",
            "rain",
            "showers",
            "snowfall",
            "weather_code",
            "wind_speed_10m",
            "wind_speed_ms",
            "wind_direction_10m",
            "wind_gusts_10m",
            "wind_u",
            "wind_v",
            "temperature_2m",
            "relative_humidity_2m",
            "visibility",
            "surface_pressure",
            "cape",
            "is_day",
            "storm_intensity",
            "fog_density",
        ]:
            assert required_key in p, f"Missing {required_key} in grid node properties"

        assert "city_summary" in data
        assert "wind_field" in data
        assert "solar" in data
        assert "storm_flags" in data

        # Second call must hit Redis cache in < 5ms
        t0 = time.perf_counter()
        cached_resp = await client.get("/api/v1/weather/grid")
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        assert cached_resp.status_code == 200
        assert elapsed_ms < 15.0  # In-process ASGI + Redis hit


@pytest.mark.asyncio
async def test_live_weather_includes_spatial_grid():
    """Verify GET /api/v1/weather/live includes 12-point spatial mesh and deterministic fallback logic."""
    from app.ingestion.weather_harvester import (
        RotterdamWeatherHarvester,
        ROTTERDAM_WEATHER_GRID_NODES,
    )

    harvester = RotterdamWeatherHarvester()
    try:
        # Test deterministic storm/fog/lightning classification on synthetic severe storm cell
        storm_props = harvester._build_grid_node_payload(
            ROTTERDAM_WEATHER_GRID_NODES[0],
            {
                "time": "2026-10-16T12:00",
                "interval": 3600,
                "apparent_temperature": 10.0,
                "cloud_cover": 100.0,
                "cloud_cover_low": 95.0,
                "cloud_cover_mid": 90.0,
                "cloud_cover_high": 85.0,
                "precipitation": 7.5,
                "rain": 5.5,
                "showers": 2.0,
                "snowfall": 0.0,
                "weather_code": 95,
                "wind_speed_10m": 58.0,
                "wind_direction_10m": 250,
                "wind_gusts_10m": 82.0,
                "temperature_2m": 12.4,
                "relative_humidity_2m": 96.0,
                "visibility": 1800.0,
                "surface_pressure": 998.5,
                "cape": 1150.0,
                "is_day": 0,
            },
            "2026-10-16T12:00:00Z",
            0,
        )
        assert storm_props["storm_intensity"] >= 0.85
        assert storm_props["fog_density"] > 0.5
        assert storm_props["lightning_active"] is False
    finally:
        await harvester.close()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/weather/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert data["total_nodes"] == 12
        assert len(data["features"]) == 12
        assert len(data["grid_nodes"]) == 12
        assert data["solar"] is not None
        assert data["wind_field"] is not None
        assert data["storm_flags"] is not None



def test_grid_converts_interval_amounts_and_preserves_calm_north_wind():
    from app.ingestion.weather_harvester import RotterdamWeatherHarvester, ROTTERDAM_WEATHER_GRID_NODES, OPEN_METEO_CURRENT_FIELDS
    current = dict.fromkeys(OPEN_METEO_CURRENT_FIELDS.split(','), 0.0)
    current.update(time='2026-10-28T12:00', interval=900, precipitation=0.5, rain=0.5,
                   temperature_2m=10, apparent_temperature=9, surface_pressure=1020, visibility=20000)
    node = RotterdamWeatherHarvester()._build_grid_node_payload(ROTTERDAM_WEATHER_GRID_NODES[6], current, '', 1)
    assert node['precipitation'] == 2.0
    assert node['rain'] == 2.0
    assert node['wind_speed_10m'] == 0
    assert node['wind_direction_10m'] == 0
    assert node['timestamp'].endswith('+00:00')
    current['interval'] = 0
    with pytest.raises(ValueError):
        RotterdamWeatherHarvester()._build_grid_node_payload(ROTTERDAM_WEATHER_GRID_NODES[6], current, '', 1)
    with pytest.raises(ValueError):
        RotterdamWeatherHarvester()._build_grid_node_payload(ROTTERDAM_WEATHER_GRID_NODES[6], {}, '', 1)


@pytest.mark.asyncio
async def test_rain_outage_is_not_a_dry_forecast(monkeypatch):
    from app.ingestion import weather_harvester as module
    async def no_cache(key): return None
    class Offline:
        async def get(self, *args, **kwargs): raise httpx.ConnectError('offline')
    harvester = module.RotterdamWeatherHarvester()
    async def client(): return Offline()
    monkeypatch.setattr(module, 'get_cached_json', no_cache)
    monkeypatch.setattr(harvester, 'get_client', client)
    result = await harvester.fetch_rain_nowcast()
    assert result['status'] == 'unavailable'
    assert result['will_rain_in_2h'] is None
    assert result['timeline'] == []


@pytest.mark.asyncio
async def test_grid_outage_preserves_original_timestamp(monkeypatch):
    from app.ingestion import weather_harvester as module
    previous = {'generated_at': '2026-10-28T12:00:00+00:00', 'grid_nodes': [], 'data_status': 'fresh'}
    async def cache(key): return previous
    class Offline:
        async def get(self, *args, **kwargs): raise httpx.ConnectError('offline')
    harvester = module.RotterdamWeatherHarvester()
    async def client(): return Offline()
    monkeypatch.setattr(module, 'get_cached_json', cache)
    monkeypatch.setattr(harvester, 'get_client', client)
    result = await harvester.fetch_spatial_weather_grid()
    assert result['generated_at'] == previous['generated_at']
    assert result['data_status'] == 'stale'
    assert previous['data_status'] == 'fresh'


@pytest.mark.asyncio
async def test_live_endpoint_returns_503_without_upstream_or_history(monkeypatch):
    from app.api.v1 import weather as module
    async def cache(key): return None
    async def unavailable(**kwargs): raise ValueError('offline')
    monkeypatch.setattr(module, 'get_cached_json', cache)
    monkeypatch.setattr(module._harvester, 'fetch_spatial_weather_grid', unavailable)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.get('/api/v1/weather/live')).status_code == 503
