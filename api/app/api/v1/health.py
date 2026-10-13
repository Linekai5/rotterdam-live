"""Healthcheck endpoints (/health/live, /health/ready)."""
from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter, Response, status
from sqlalchemy import text
from app.db.session import engine
from app.cache.redis_client import get_redis_client

router = APIRouter(prefix="/health", tags=["Health & Observability"])


@router.get("/live")
async def health_live() -> Dict[str, Any]:
    """Liveness probe: verifies process is alive and receiving HTTP requests."""
    return {
        "status": "alive",
        "service": "rotterdam-live-api",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready")
async def health_ready(response: Response) -> Dict[str, Any]:
    """
    Readiness probe: checks database connectivity and Redis cache readiness.
    Returns HTTP 200 if operational, HTTP 503 if critical dependencies are down.
    """
    db_ok = False
    redis_ok = False
    db_error = None
    redis_error = None

    # 1. Check PostgreSQL
    try:
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT 1"))
            if res.scalar() == 1:
                db_ok = True
    except Exception as e:
        db_error = str(e)

    # 2. Check Redis
    try:
        client = await get_redis_client()
        if client and await client.ping():
            redis_ok = True
    except Exception as e:
        redis_error = str(e)

    is_ready = db_ok
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if is_ready else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": {"connected": db_ok, "error": db_error},
        "redis": {"connected": redis_ok, "error": redis_error},
    }
