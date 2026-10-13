"""Tests for FastAPI HTTP endpoints and middleware."""
import pytest
import httpx
from app.main import app


@pytest.mark.asyncio
async def test_root_endpoint():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "Rotterdam Live" in data["service"]
        assert "endpoints" in data


@pytest.mark.asyncio
async def test_health_live():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/health/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "alive"


@pytest.mark.asyncio
async def test_security_and_performance_headers():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/")
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
        assert "x-process-time-ms" in resp.headers


@pytest.mark.asyncio
async def test_invalid_bbox_validation():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Invalid bbox format
        resp = await client.get("/api/v1/emergencies?bbox=invalid,bbox")
        assert resp.status_code == 400
        assert "Invalid bbox parameter" in resp.json()["detail"]
