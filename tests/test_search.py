"""Tests for Rotterdam Live Global Spatial Search API endpoints."""
import pytest
import httpx
from app.main import app


@pytest.mark.asyncio
async def test_global_search_address():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/search?q=Coolsingel&types=address&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert "features" in data
        assert "total_results" in data


@pytest.mark.asyncio
async def test_global_search_retail():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/search?q=Albert%20Heijn&types=retail&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) > 0
        feat = data["features"][0]
        assert feat["properties"]["entity_type"] == "retail"
        assert "Albert Heijn" in feat["properties"]["title"]


@pytest.mark.asyncio
async def test_global_search_combined():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/search?q=Centrum&types=address,retail,amenity&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
