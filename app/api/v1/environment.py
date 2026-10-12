"""Environment, Weather & Air Quality API router (/api/v1/environment)."""
from typing import Optional, Tuple
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import parse_bbox_param
from app.db.session import get_db
from app.schemas.geojson import GeoJSONFeatureCollection
from app.services.spatial_service import query_live_events
from app.cache.redis_client import get_cached_json, set_cached_json, quantize_bbox

router = APIRouter(prefix="/environment", tags=["Environment & Air Quality"])


@router.get("", response_model=GeoJSONFeatureCollection)
async def get_environment(
    subcategory: Optional[str] = Query(
        None, description="Filter by subcategory: weather, air_quality"
    ),
    district: Optional[str] = Query(
        None, description="Filter by district"
    ),
    bbox: Optional[Tuple[float, float, float, float]] = Depends(parse_bbox_param),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> GeoJSONFeatureCollection:
    """
    Get live environmental metrics: Open-Meteo weather parameters and
    Luchtmeetnet / DCMR air quality stations across Rotterdam.
    Served in < 30ms from local cache and PostGIS database.
    """
    bbox_str = quantize_bbox(*bbox) if bbox else "none"
    cache_key = f"events:env:{bbox_str}:{subcategory}:{district}:{limit}:{offset}"

    cached = await get_cached_json(cache_key)
    if cached:
        return GeoJSONFeatureCollection.model_validate(cached)

    result = await query_live_events(
        session=session,
        category="environment",
        subcategory=subcategory,
        district=district,
        active_only=True,
        bbox=bbox,
        limit=limit,
        offset=offset,
    )

    await set_cached_json(cache_key, result.model_dump(mode="json"), ttl_seconds=60)
    return result
