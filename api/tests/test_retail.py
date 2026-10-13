"""Tests for Rotterdam Retail Infrastructure & Commercial Facilities API endpoints."""
import pytest
import httpx
from app.main import app


@pytest.mark.asyncio
async def test_retail_list():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/retail?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert "features" in data
        assert len(data["features"]) <= 10
        if data["features"]:
            feat = data["features"][0]
            assert feat["type"] == "Feature"
            assert feat["geometry"]["type"] == "Point"
            props = feat["properties"]
            assert "id" in props
            assert "name" in props
            assert "shop_type" in props


@pytest.mark.asyncio
async def test_retail_stats():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/retail/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_venues" in data
        assert data["total_venues"] > 0
        assert "categories" in data
        assert "supermarkets_count" in data
        assert "bag_linked_count" in data


@pytest.mark.asyncio
async def test_supermarkets_endpoint():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/retail/supermarkets?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        for feat in data["features"]:
            assert feat["properties"]["shop_type"] == "supermarket"


@pytest.mark.asyncio
async def test_retail_filter_by_brand():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/retail?brand=Albert%20Heijn&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"


@pytest.mark.asyncio
async def test_retail_not_found():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/retail/non_existent_retail_12345")
        assert resp.status_code == 404
