"""Redis caching client with bounding-box quantization, TTLs, and resilience."""
import json
from typing import Any, Optional
import redis.asyncio as aioredis
from app.config import settings
from app.logging import logger

_redis_client: Optional[aioredis.Redis] = None


async def get_redis_client() -> Optional[aioredis.Redis]:
    """Get or initialize singleton Redis client."""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                max_connections=20,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
            )
            # Test ping
            await _redis_client.ping()
            logger.info("Successfully connected to Redis at {}", settings.REDIS_URL)
        except Exception as e:
            logger.warning(
                "Redis connection failed ({}), operating in fallback cache mode", e
            )
            _redis_client = None
    return _redis_client


async def close_redis_client() -> None:
    """Close Redis connection cleanly."""
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.close()
        except Exception:
            pass
        _redis_client = None


def quantize_bbox(
    min_lon: float, min_lat: float, max_lon: float, max_lat: float, precision: int = 3
) -> str:
    """
    Quantize bounding-box coordinates to ~100m grid for high cache-hit ratio
    during map viewport pans and zooms.
    """
    q_min_lon = round(min_lon, precision)
    q_min_lat = round(min_lat, precision)
    q_max_lon = round(max_lon, precision)
    q_max_lat = round(max_lat, precision)
    return f"{q_min_lon}:{q_min_lat}:{q_max_lon}:{q_max_lat}"


async def get_cached_json(key: str) -> Optional[Any]:
    """Retrieve JSON-deserialized object from Redis cache."""
    try:
        client = await get_redis_client()
        if client:
            val = await client.get(key)
            if val:
                return json.loads(val)
    except Exception as e:
        logger.debug("Redis cache read error for key {}: {}", key, e)
    return None


async def set_cached_json(key: str, data: Any, ttl_seconds: int = 15) -> bool:
    """Store serializable object into Redis cache with TTL."""
    try:
        client = await get_redis_client()
        if client:
            serialized = json.dumps(data)
            await client.set(key, serialized, ex=ttl_seconds)
            return True
    except Exception as e:
        logger.debug("Redis cache write error for key {}: {}", key, e)
    return False


async def delete_cache_pattern(pattern: str) -> int:
    """Invalidate cache keys matching a pattern."""
    try:
        client = await get_redis_client()
        if client:
            keys = await client.keys(pattern)
            if keys:
                return await client.delete(*keys)
    except Exception as e:
        logger.debug("Redis cache invalidation error: {}", e)
    return 0
