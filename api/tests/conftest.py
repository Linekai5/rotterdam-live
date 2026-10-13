"""Pytest fixtures and configuration for Rotterdam Live API test suite."""
import pytest
from app.db.session import engine
from app.cache.redis_client import close_redis_client
from app.api.v1.weather import _harvester


@pytest.fixture(autouse=True)
async def cleanup_connections():
    """Ensure db engine connection pool, redis client, and weather harvester are cleanly closed after each test."""
    yield
    await engine.dispose()
    await close_redis_client()
    await _harvester.close()
