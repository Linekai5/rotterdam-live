"""Tests for Official Kadaster BAG Addresses API endpoints."""
import pytest
import httpx
from app.main import app


@pytest.mark.asyncio
async def test_addresses_list():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/addresses?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert "features" in data
        assert len(data["features"]) <= 10
        if data["features"]:
            feat = data["features"][0]
            assert feat["type"] == "Feature"
            assert feat["geometry"]["type"] == "Point"
            assert len(feat["geometry"]["coordinates"]) == 2
            props = feat["properties"]
            assert "address_id" in props
            assert "street_name" in props
            assert "house_number" in props
            assert "postal_code" in props
            assert "display_name" in props


@pytest.mark.asyncio
async def test_addresses_stats():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/addresses/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_addresses" in data
        assert data["total_addresses"] > 0
        assert "purposes" in data
        assert "districts" in data


@pytest.mark.asyncio
async def test_addresses_search():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Search by street name
        resp = await client.get("/api/v1/addresses/search?q=Coolsingel&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert "features" in data


@pytest.mark.asyncio
async def test_addresses_filter_by_district():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/addresses?district=Centrum&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"


@pytest.mark.asyncio
async def test_address_not_found():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/addresses/non_existent_0599000000000000")
        assert resp.status_code == 404
