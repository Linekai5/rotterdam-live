"""FastAPI Router for Utility, Electricity Grid, and Infrastructure Status."""
from typing import Optional
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, parse_bbox_param
from app.cache.redis_client import get_redis_client
from app.schemas.geojson import GeoJSONFeatureCollection
from app.services.spatial_service import query_live_events
from app.logging import logger

router = APIRouter(prefix="/utilities", tags=["Utilities & Grid"])


@router.get("/power-outages", response_model=GeoJSONFeatureCollection)
async def get_power_outages(
    district: Optional[str] = Query(None, description="Filter by Rotterdam district"),
    bbox: Optional[str] = Query(None, description="Bounding box: min_lon,min_lat,max_lon,max_lat"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    """
    Active electrical grid outages, substation operational status,
    and regional grid indicators across Rotterdam (Stedin).
    """
    bbox_coords = parse_bbox_param(bbox)
    cache_key = f"utilities:power:{district}:{bbox}:{limit}:{offset}"
    redis = await get_redis_client()

    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return Response(content=cached, media_type="application/json")
        except Exception:
            pass

    geojson = await query_live_events(
        session=session,
        category="utility",
        subcategory="power_outage",
        district=district,
        bbox=bbox_coords,
        limit=limit,
        offset=offset,
        active_only=True,
    )

    if redis:
        try:
            await redis.setex(cache_key, 300, geojson.model_dump_json())
        except Exception:
            pass

    return geojson
