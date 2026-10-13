"""Emergencies & Public Safety API router (/api/v1/emergencies)."""
from typing import Optional, Tuple
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import parse_bbox_param
from app.db.session import get_db
from app.schemas.geojson import GeoJSONFeatureCollection
from app.services.spatial_service import query_live_events
from app.cache.redis_client import get_cached_json, set_cached_json, quantize_bbox

router = APIRouter(prefix="/emergencies", tags=["Emergencies & Public Safety"])


@router.get("", response_model=GeoJSONFeatureCollection)
async def get_emergencies(
    subcategory: Optional[str] = Query(
        None,
        description="Filter by discipline: brandweer, ambulance, politie, traumahelikopter",
    ),
    district: Optional[str] = Query(
        None, description="Filter by Rotterdam district (e.g. Centrum, Delfshaven)"
    ),
    min_severity: Optional[int] = Query(
        None, ge=1, le=5, description="Filter by minimum severity level (1-5)"
    ),
    active_only: bool = Query(
        True, description="Only return active unexpired incidents"
    ),
    bbox: Optional[Tuple[float, float, float, float]] = Depends(parse_bbox_param),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> GeoJSONFeatureCollection:
    """
    Get live emergency incidents (P2000 Alarmeringen for Rotterdam-Rijnmond).
    Served strictly from local PostGIS database & Redis cache in < 30ms.
    """
    # Cache key generation
    bbox_str = quantize_bbox(*bbox) if bbox else "none"
    cache_key = f"events:emergency:{bbox_str}:{subcategory}:{district}:{min_severity}:{active_only}:{limit}:{offset}"

    cached = await get_cached_json(cache_key)
    if cached:
        return GeoJSONFeatureCollection.model_validate(cached)

    result = await query_live_events(
        session=session,
        category="emergency",
        subcategory=subcategory,
        district=district,
        min_severity=min_severity,
        active_only=active_only,
        bbox=bbox,
        limit=limit,
        offset=offset,
    )

    await set_cached_json(cache_key, result.model_dump(mode="json"), ttl_seconds=15)
    return result
