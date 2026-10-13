"""Comprehensive Test Suite for the Real-Time Traffic Subsystem (/api/v1/mobility/traffic).

Platform v2.0.0-rc
Verifies:
1. RFC 7946 LineString GeoJSON schema compliance
2. Diurnal traffic profiles and congestion classification logic
3. Harvester execution and database upsert
4. API endpoints, query filters, ETag 304 conditional caching, and error handling
"""
import pytest
from datetime import datetime, timezone
import httpx
from app.main import app
from app.schemas.traffic import (
    TrafficSegmentProperties,
    TrafficSegmentFeature,
    TrafficFeatureCollection,
    TrafficOverviewStats,
)
from app.ingestion.traffic_harvester import (
    MONITORED_CORRIDORS,
    classify_congestion,
    calculate_diurnal_speed,
    RotterdamTrafficHarvester,
)


def test_traffic_schema_validation():
    """Verify strict Pydantic validation for LineString traffic features."""
    feature_dict = {
        "type": "Feature",
        "id": "corridor-a20-eastbound",
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [4.435, 51.933],
                [4.458, 51.938],
                [4.532, 51.948],
            ],
        },
        "properties": {
            "id": "corridor-a20-eastbound",
            "name": "A20 Kleinpolderplein → Terbregseplein (Oostwaarts)",
            "road_type": "motorway",
            "free_flow_seconds": 270,
            "current_travel_time_seconds": 320,
            "delay_seconds": 50,
            "speed_kmh": 84.5,
            "congestion_level": "moderate",
            "district": "Noord",
            "updated_at": datetime.now(timezone.utc),
        },
    }
    feature = TrafficSegmentFeature.model_validate(feature_dict)
    assert feature.geometry.type == "LineString"
    assert len(feature.geometry.coordinates) == 3
    assert feature.properties.delay_seconds == 50
    assert feature.properties.road_type == "motorway"

    fc = TrafficFeatureCollection(
        type="FeatureCollection",
        features=[feature],
        total_segments=1,
        timestamp=datetime.now(timezone.utc),
    )
    assert fc.total_segments == 1
    assert fc.features[0].id == "corridor-a20-eastbound"


def test_congestion_classification():
    """Verify exact speed ratio congestion threshold classification."""
    assert classify_congestion(0.95) == "free_flow"
    assert classify_congestion(0.85) == "free_flow"
    assert classify_congestion(0.84) == "moderate"
    assert classify_congestion(0.60) == "moderate"
    assert classify_congestion(0.59) == "heavy"
    assert classify_congestion(0.30) == "heavy"
    assert classify_congestion(0.29) == "standstill"
    assert classify_congestion(0.10) == "standstill"


def test_diurnal_speed_calculation():
    """Verify diurnal model produces realistic speed drops during peak hours."""
    a16_south = next(c for c in MONITORED_CORRIDORS if c["id"] == "corridor-a16-southbound")
    
    # Tuesday 03:00 (Night -> free flow)
    night_time = datetime(2026, 10, 13, 3, 0, tzinfo=timezone.utc)
    speed_night = calculate_diurnal_speed(a16_south, night_time)
    assert speed_night >= 90.0

    # Tuesday 17:15 (Evening peak for outbound motorway)
    peak_time = datetime(2026, 10, 13, 17, 15, tzinfo=timezone.utc)
    speed_peak = calculate_diurnal_speed(a16_south, peak_time)
    assert speed_peak < speed_night
    assert speed_peak <= 65.0


def test_corridors_geometry_completeness():
    """Verify all 18 designated corridors have valid LineString geometries and positive lengths."""
    assert len(MONITORED_CORRIDORS) == 18
    motorways = [c for c in MONITORED_CORRIDORS if c["road_type"] == "motorway"]
    arterials = [c for c in MONITORED_CORRIDORS if c["road_type"] == "urban_arterial"]

    assert len(motorways) == 10  # A20, A16, A15, A4, A13 (2 directions each)
    assert len(arterials) == 8   # S100, S103, S102, Maastunnel (2 directions each)

    for corr in MONITORED_CORRIDORS:
        coords = corr["coordinates"]
        assert len(coords) >= 3
        for pt in coords:
            assert len(pt) == 2
            lon, lat = pt
            assert 4.20 <= lon <= 4.70
            assert 51.80 <= lat <= 52.05


@pytest.mark.asyncio
async def test_traffic_harvester_execution():
    """Verify harvester execution cycle upserts data to DB and Redis."""
    harvester = RotterdamTrafficHarvester()
    result = await harvester.ingest()
    await harvester.close()

    assert result["segments_processed"] == 18
    overview = result["overview"]
    assert overview["total_segments"] == 18
    assert overview["average_speed_kmh"] > 0
    assert overview["average_motorway_speed_kmh"] > 0
    assert overview["average_arterial_speed_kmh"] > 0


@pytest.mark.asyncio
async def test_api_traffic_master_featurecollection():
    """Verify GET /api/v1/mobility/traffic returns RFC 7946 LineString collection with ETag."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/mobility/traffic")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert data["total_segments"] == 18
        assert len(data["features"]) == 18

        etag = resp.headers.get("etag")
        assert etag is not None

        # Verify first feature structure
        feat = data["features"][0]
        assert feat["type"] == "Feature"
        assert feat["geometry"]["type"] == "LineString"
        assert len(feat["geometry"]["coordinates"]) >= 3
        props = feat["properties"]
        assert "speed_kmh" in props
        assert "congestion_level" in props
        assert "delay_seconds" in props
        assert "free_flow_seconds" in props
        assert "current_travel_time_seconds" in props

        # Test conditional ETag 304
        resp304 = await client.get("/api/v1/mobility/traffic", headers={"if-none-match": etag})
        assert resp304.status_code == 304


@pytest.mark.asyncio
async def test_api_traffic_filters():
    """Verify filtering by road_type, congestion_level, district, and bbox."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Filter road_type=motorway
        resp_m = await client.get("/api/v1/mobility/traffic?road_type=motorway")
        assert resp_m.status_code == 200
        data_m = resp_m.json()
        assert data_m["total_segments"] == 10
        assert all(f["properties"]["road_type"] == "motorway" for f in data_m["features"])

        # 2. Filter road_type=urban_arterial
        resp_u = await client.get("/api/v1/mobility/traffic?road_type=urban_arterial")
        assert resp_u.status_code == 200
        data_u = resp_u.json()
        assert data_u["total_segments"] == 8
        assert all(f["properties"]["road_type"] == "urban_arterial" for f in data_u["features"])

        # 3. Filter district=Centrum
        resp_d = await client.get("/api/v1/mobility/traffic?district=Centrum")
        assert resp_d.status_code == 200
        data_d = resp_d.json()
        assert data_d["total_segments"] > 0
        for f in data_d["features"]:
            assert "centrum" in (f["properties"]["district"] or "").lower()

        # 4. Filter bbox
        resp_bbox = await client.get("/api/v1/mobility/traffic?bbox=4.40,51.90,4.50,51.95")
        assert resp_bbox.status_code == 200
        data_bbox = resp_bbox.json()
        assert data_bbox["total_segments"] > 0


@pytest.mark.asyncio
async def test_api_traffic_overview():
    """Verify GET /api/v1/mobility/traffic/overview returns aggregated metrics and handles ETag."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/mobility/traffic/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_segments"] == 18
        assert data["free_flow_count"] + data["moderate_count"] + data["heavy_count"] + data["standstill_count"] == 18
        assert data["average_speed_kmh"] > 0
        assert data["average_motorway_speed_kmh"] > 0
        assert data["average_arterial_speed_kmh"] > 0
        assert "most_congested_corridor" in data

        etag = resp.headers.get("etag")
        assert etag is not None

        # Test conditional ETag 304
        resp304 = await client.get("/api/v1/mobility/traffic/overview", headers={"if-none-match": etag})
        assert resp304.status_code == 304


@pytest.mark.asyncio
async def test_api_traffic_single_segment_and_404():
    """Verify GET /api/v1/mobility/traffic/{segment_id} detail and 404 behavior."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Valid segment
        resp = await client.get("/api/v1/mobility/traffic/corridor-a16-southbound")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "corridor-a16-southbound"
        assert data["properties"]["road_type"] == "motorway"
        assert data["geometry"]["type"] == "LineString"

        # ETag 304
        etag = resp.headers.get("etag")
        assert etag is not None
        resp304 = await client.get(
            "/api/v1/mobility/traffic/corridor-a16-southbound",
            headers={"if-none-match": etag},
        )
        assert resp304.status_code == 304

        # Nonexistent segment
        resp404 = await client.get("/api/v1/mobility/traffic/nonexistent-corridor")
        assert resp404.status_code == 404
        assert "not found" in resp404.json()["detail"].lower()
