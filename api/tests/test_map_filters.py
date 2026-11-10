"""Map filter contracts using transactional, isolated PostGIS camera records."""
import json

import httpx
import pytest
from sqlalchemy import text

from app.api.v1 import amenities
from app.db.session import AsyncSessionLocal, get_db
from app.main import app
from app.ingestion.camera_harvester import camera_record_from_osm, retire_unsupported_camera_records


@pytest.fixture
async def camera_database():
    async with AsyncSessionLocal() as session:
        await session.execute(text(
            "CREATE TEMP TABLE city_amenities "
            "(LIKE public.city_amenities INCLUDING DEFAULTS) ON COMMIT DROP"
        ))
        try:
            yield session
        finally:
            await session.rollback()


@pytest.fixture
async def camera_client(monkeypatch, camera_database):
    async def no_cache():
        return None

    monkeypatch.setattr(amenities, "get_redis_client", no_cache)
    session = camera_database
    cases = {
        "declared-live": {"has_live_feed": True},
        "legacy-stream": {"has_live_feed": False, "stream_url": "https://example.com/live"},
        "snapshot": {"snapshot_url": "https://example.com/view.jpg"},
        "closed": {"has_live_feed": False},
        "unknown": {},
        "empty-urls": {"snapshot_url": "", "stream_url": "   "},
        "null-values": {"has_live_feed": None, "snapshot_url": None},
    }
    await session.execute(text("""
        INSERT INTO city_amenities
            (id, category, subcategory, name, details, geom, is_active, created_at, updated_at)
        VALUES (:id, 'amenity', 'camera', :id, CAST(:details AS JSONB),
                ST_SetSRID(ST_Point(4.48, 51.92), 4326), TRUE, NOW(), NOW())
    """), [
        {"id": name, "details": json.dumps({"camera_type": "skyline_webcam", **details})}
        for name, details in cases.items()
    ])

    async def database():
        yield session

    app.dependency_overrides[get_db] = database
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_camera_feed_filters_are_disjoint_and_exhaustive(camera_client):
    results = {}
    for value in ["true", "false", None]:
        params = {"camera_type": "skyline_webcam", "bbox": "4.4,51.9,4.6,52.0"}
        if value is not None:
            params["has_live_feed"] = value
        response = await camera_client.get("/api/v1/amenities/cameras", params=params)
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "FeatureCollection"
        results[value] = {feature["properties"]["id"] for feature in data["features"]}

    assert results["true"] == {"declared-live", "legacy-stream", "snapshot"}
    assert results["false"] == {"closed", "unknown", "empty-urls", "null-values"}
    assert not results["true"] & results["false"]
    assert results["true"] | results["false"] == results[None]
    live = await camera_client.get("/api/v1/amenities/cameras/live")
    assert live.status_code == 200
    assert {feature["properties"]["id"] for feature in live.json()["features"]} == results["true"]


@pytest.mark.asyncio
async def test_camera_category_and_viewport_filters_compose(camera_client):
    for params in [
        {"camera_type": "traffic"},
        {"camera_type": "skyline_webcam", "bbox": "4.0,51.0,4.1,51.1"},
    ]:
        response = await camera_client.get("/api/v1/amenities/cameras", params=params)
        assert response.status_code == 200
        assert response.json()["features"] == []

    invalid = await camera_client.get("/api/v1/amenities/cameras?bbox=broken")
    assert invalid.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("bbox", [
    "broken", "4.6,51.9,4.4,52.0", "181,51.9,182,52.0",
    "nan,51.9,4.6,52.0", "4.4,51.9,4.6",
])
async def test_retail_rejects_invalid_viewports_before_querying(bbox):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/retail", params={"bbox": bbox})
    assert response.status_code == 400
    assert "Invalid bbox" in response.json()["detail"]


@pytest.mark.parametrize("tags", [
    {"amenity": "restaurant"}, {"shop": "supermarket"}, {"barrier": "gate"},
    {"tourism": "viewpoint"}, {"surveillance": "no"},
    {"man_made": "surveillance", "indoor": "yes"},
])
def test_camera_directory_never_infers_devices_from_venues(tags):
    assert camera_record_from_osm({"id": 123, "lon": 4.48, "lat": 51.92, "tags": tags}) is None


def test_camera_location_source_does_not_imply_public_video():
    record = camera_record_from_osm({
        "id": 123, "lon": 4.48, "lat": 51.92,
        "tags": {"man_made": "surveillance", "snapshot_url": "https://example.com/guessed.jpg"},
    })
    assert record["id"] == "camera-123"
    assert record["details"]["source_url"] == "https://www.openstreetmap.org/node/123"
    assert record["details"]["has_live_feed"] is False
    assert record["details"]["snapshot_url"] is None
    assert record["details"]["feed_status"] == "not_provided"


@pytest.mark.asyncio
async def test_camera_repair_preserves_source_records_and_retires_inferred_duplicates(camera_database):
    session = camera_database
    cases = {
        "camera-123": {"osm_id": "123", "camera_type": "CCTV"},
        "cam-osm-n123": {"osm_id": "n123", "source": "Rotterdam Camera Engine", "venue_type": "public_security"},
        "cam-osm-n456": {"osm_id": "n456", "source": "Rotterdam Camera Engine", "venue_type": "public_security"},
        "cam-osm-n789": {"osm_id": "n789", "source": "Rotterdam Camera Engine", "venue_type": "hospitality_restaurant"},
        "cam-webcam-fake": {"source": "Rotterdam Camera Engine", "has_live_feed": True, "snapshot_url": "https://example.com/fake.jpg"},
        "camera-cam-cs-plein": {},
        "other-provider-camera": {"source": "Other provider", "has_live_feed": True},
    }
    await session.execute(text("""
        INSERT INTO city_amenities (id, category, subcategory, name, details, geom, is_active, created_at, updated_at)
        VALUES (:id, 'amenity', 'camera', :id, CAST(:details AS JSONB),
                ST_SetSRID(ST_Point(4.48, 51.92), 4326), TRUE, NOW(), NOW())
    """), [{"id": name, "details": json.dumps(details)} for name, details in cases.items()])
    assert await retire_unsupported_camera_records(session) == 4
    result = await session.execute(text("SELECT id, details FROM city_amenities WHERE is_active"))
    active = {row.id: row.details for row in result}
    assert set(active) == {"camera-123", "cam-osm-n456", "other-provider-camera"}
    assert active["camera-123"]["source_url"] == "https://www.openstreetmap.org/node/123"
    assert active["cam-osm-n456"]["source_url"] == "https://www.openstreetmap.org/node/456"
    assert active["camera-123"]["camera_type"] == "surveillance"
    assert active["other-provider-camera"] == {"source": "Other provider", "has_live_feed": True}
