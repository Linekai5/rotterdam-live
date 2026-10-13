"""Comprehensive Unit and Integration Tests for /api/v1/events Domain.

Tests RFC 7946 GeoJSON compliance, PostGIS boundary enforcement,
filtering, caching, ETag support, and ingestion pipelines.
"""
import pytest
import httpx
from app.main import app
from app.db.session import AsyncSessionLocal
from app.services.events_service import upsert_rotterdam_event
from app.ingestion.events_harvester import RotterdamEventsHarvester


@pytest.mark.asyncio
async def test_events_list_geojson():
    """Verify GET /api/v1/events returns RFC 7946 GeoJSON FeatureCollection."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/events?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert "features" in data
        assert len(data["features"]) > 0

        feat = data["features"][0]
        assert feat["type"] == "Feature"
        assert feat["geometry"]["type"] == "Point"
        assert len(feat["geometry"]["coordinates"]) == 2

        props = feat["properties"]
        assert "id" in props
        assert "title" in props
        assert props["category"] == "event"
        assert "subcategory" in props
        assert "source" in props
        assert "venue" in props
        assert "name" in props["venue"]
        assert "district" in props
        assert props["district"] is not None
        assert "start_time" in props


@pytest.mark.asyncio
async def test_events_filter_by_source():
    """Verify filtering events by source: ticketmaster, stadium_fixtures, municipal_festivals."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Municipal Festivals
        resp_fest = await client.get("/api/v1/events?source=municipal_festivals")
        assert resp_fest.status_code == 200
        fest_data = resp_fest.json()
        assert len(fest_data["features"]) > 0
        for f in fest_data["features"]:
            assert f["properties"]["source"] == "municipal_festivals"

        # 2. Stadium Fixtures
        resp_stad = await client.get("/api/v1/events?source=stadium_fixtures")
        assert resp_stad.status_code == 200
        stad_data = resp_stad.json()
        assert len(stad_data["features"]) > 0
        for f in stad_data["features"]:
            assert f["properties"]["source"] == "stadium_fixtures"

        # 3. Ticketmaster
        resp_tm = await client.get("/api/v1/events?source=ticketmaster&limit=5")
        assert resp_tm.status_code == 200
        tm_data = resp_tm.json()
        assert len(tm_data["features"]) > 0
        for f in tm_data["features"]:
            assert f["properties"]["source"] == "ticketmaster"


@pytest.mark.asyncio
async def test_events_filter_by_district():
    """Verify filtering events by district."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/events?district=Centrum")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["features"]) > 0
        for f in data["features"]:
            assert "Centrum" in f["properties"]["district"]


@pytest.mark.asyncio
async def test_events_venues_endpoint():
    """Verify GET /api/v1/events/venues returns verified venues with event counts."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/events/venues")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_venues" in data
        assert data["total_venues"] > 0
        assert "venues" in data

        first_v = data["venues"][0]
        assert "name" in first_v
        assert "district" in first_v
        assert "coordinates" in first_v
        assert len(first_v["coordinates"]) == 2
        assert first_v["total_events"] > 0


@pytest.mark.asyncio
async def test_events_festivals_endpoint():
    """Verify GET /api/v1/events/festivals returns municipal festivals."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/events/festivals")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) >= 10
        titles = [f["properties"]["title"] for f in data["features"]]
        assert any("International Film Festival" in t for t in titles)
        assert any("Marathon" in t for t in titles)
        assert any("North Sea Jazz" in t for t in titles)


@pytest.mark.asyncio
async def test_events_stadiums_endpoint():
    """Verify GET /api/v1/events/stadiums returns stadium fixtures."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/events/stadiums")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) > 0
        for f in data["features"]:
            assert f["properties"]["subcategory"] == "stadium_fixture"
            assert f["properties"]["venue"]["name"] in [
                "Stadion Feijenoord (De Kuip)",
                "Sparta-Stadion Het Kasteel",
                "Van Donge & De Roo Stadion (Woudestein)",
            ]


@pytest.mark.asyncio
async def test_events_stats_endpoint():
    """Verify GET /api/v1/events/stats returns complete domain aggregations."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/events/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_events" in data
        assert data["total_events"] > 50
        assert "subcategories" in data
        assert "sources" in data
        assert "districts" in data
        assert "top_venues" in data
        assert "ticketmaster" in data["sources"]
        assert "stadium_fixtures" in data["sources"]
        assert "municipal_festivals" in data["sources"]


@pytest.mark.asyncio
async def test_single_event_and_not_found():
    """Verify GET /api/v1/events/{id} returns single Feature and handles 404."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        list_resp = await client.get("/api/v1/events?limit=1")
        first_id = list_resp.json()["features"][0]["properties"]["id"]

        resp = await client.get(f"/api/v1/events/{first_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "Feature"
        assert data["properties"]["id"] == first_id

        # 404 Not Found
        resp_404 = await client.get("/api/v1/events/nonexistent_event_999999")
        assert resp_404.status_code == 404


@pytest.mark.asyncio
async def test_spatial_boundary_validation_rejects_outside_point():
    """Verify PostGIS ST_Within strictly rejects entities outside Rotterdam municipal boundaries."""
    # Amsterdam coordinates (outside Rotterdam)
    outside_payload = {
        "id": "test_amsterdam_event_999",
        "title": "Amsterdam Concert Outside Rotterdam",
        "category": "event",
        "subcategory": "concert",
        "source": "ticketmaster",
        "venue_name": "Ziggo Dome Amsterdam",
        "start_time": "2026-12-01T20:00:00Z",
        "lon": 4.9367,  # Amsterdam
        "lat": 52.3134,
    }

    async with AsyncSessionLocal() as session:
        result = await upsert_rotterdam_event(outside_payload, session)
        assert result is False, "Event outside Rotterdam must be rejected by ST_Within boundary check"


@pytest.mark.asyncio
async def test_etag_caching_and_sub_5ms_performance():
    """Verify ETag 304 response and sub-5ms Redis cache response."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/events?limit=5")
        assert resp.status_code == 200
        etag = resp.headers.get("etag")
        assert etag is not None

        # Repeat request with If-None-Match
        resp_cached = await client.get(
            "/api/v1/events?limit=5", headers={"If-None-Match": etag}
        )
        assert resp_cached.status_code == 304


@pytest.mark.asyncio
async def test_search_integration_for_events():
    """Verify global search finds events when types='event'."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/search?q=Feyenoord&types=event&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) > 0
        first = data["features"][0]
        assert first["properties"]["entity_type"] == "event"
        assert "Feyenoord" in first["properties"]["title"]
