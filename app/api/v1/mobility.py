"""Mobility, Parking & Traffic API router (/api/v1/mobility)."""
from typing import Optional, Tuple
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import parse_bbox_param
from app.db.session import get_db
from app.schemas.geojson import GeoJSONFeatureCollection
from app.services.spatial_service import query_live_events
from app.cache.redis_client import get_cached_json, set_cached_json, quantize_bbox

router = APIRouter(prefix="/mobility", tags=["Mobility, Parking & Traffic"])


@router.get("", response_model=GeoJSONFeatureCollection)
async def get_mobility(
    subcategory: Optional[str] = Query(
        None,
        description="Filter by subcategory: parking, bridge, shared_mobility, public_transit",
    ),
    district: Optional[str] = Query(
        None, description="Filter by Rotterdam district"
    ),
    active_only: bool = Query(
        True, description="Only return active items"
    ),
    bbox: Optional[Tuple[float, float, float, float]] = Depends(parse_bbox_param),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> GeoJSONFeatureCollection:
    """
    Get live mobility data: parking garage occupancy, bridge opening statuses,
    micro-mobility deelfietsen, and public transit disruptions (RET / OpenOV).
    Served in < 30ms from local cache and PostGIS database.
    """
    bbox_str = quantize_bbox(*bbox) if bbox else "none"
    cache_key = f"events:mobility:{bbox_str}:{subcategory}:{district}:{active_only}:{limit}:{offset}"

    cached = await get_cached_json(cache_key)
    if cached:
        return GeoJSONFeatureCollection.model_validate(cached)

    result = await query_live_events(
        session=session,
        category="mobility",
        subcategory=subcategory,
        district=district,
        active_only=active_only,
        bbox=bbox,
        limit=limit,
        offset=offset,
    )

    await set_cached_json(cache_key, result.model_dump(mode="json"), ttl_seconds=15)
    return result


@router.get("/roadworks", response_model=GeoJSONFeatureCollection)
async def get_roadworks(
    district: Optional[str] = Query(None, description="Filter by district"),
    active_only: bool = Query(True, description="Only return active roadworks"),
    bbox: Optional[Tuple[float, float, float, float]] = Depends(parse_bbox_param),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> GeoJSONFeatureCollection:
    """
    Get active road closures, lane disruptions, and municipal roadwork permits from VGW.
    """
    bbox_str = quantize_bbox(*bbox) if bbox else "none"
    cache_key = f"events:mobility:roadworks:{bbox_str}:{district}:{active_only}:{limit}:{offset}"

    cached = await get_cached_json(cache_key)
    if cached:
        return GeoJSONFeatureCollection.model_validate(cached)

    result = await query_live_events(
        session=session,
        category="mobility",
        subcategory="roadworks",
        district=district,
        active_only=active_only,
        bbox=bbox,
        limit=limit,
        offset=offset,
    )

    await set_cached_json(cache_key, result.model_dump(mode="json"), ttl_seconds=300)
    return result
