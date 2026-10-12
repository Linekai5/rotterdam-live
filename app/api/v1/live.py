"""Unified Multi-Layer Live Feed API router (/api/v1/live)."""
import hashlib
import json
from typing import Optional, Tuple
from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import parse_bbox_param
from app.db.session import get_db
from app.schemas.geojson import GeoJSONFeatureCollection
from app.services.spatial_service import query_live_events
from app.cache.redis_client import get_cached_json, set_cached_json, quantize_bbox

router = APIRouter(prefix="/live", tags=["Unified Live Map Feed"])


@router.get("", response_model=GeoJSONFeatureCollection)
async def get_live_events(
    request: Request,
    response: Response,
    category: Optional[str] = Query(
        None,
        description="Filter by category: emergency, mobility, news, environment (or comma-separated)",
    ),
    subcategory: Optional[str] = Query(None, description="Filter by subcategory"),
    district: Optional[str] = Query(None, description="Filter by district"),
    min_severity: Optional[int] = Query(None, ge=1, le=5),
    active_only: bool = Query(True, description="Only return active unexpired events"),
    bbox: Optional[Tuple[float, float, float, float]] = Depends(parse_bbox_param),
    limit: int = Query(250, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> GeoJSONFeatureCollection:
    """
    Unified multi-layer endpoint returning all active urban intelligence events
    for the Rotterdam Live Svelte map application.
    Features sub-millisecond quantized BBOX caching and ETag conditional GET support.
    """
    bbox_str = quantize_bbox(*bbox) if bbox else "none"
    cache_key = f"events:live:{bbox_str}:{category}:{subcategory}:{district}:{min_severity}:{active_only}:{limit}:{offset}"

    cached = await get_cached_json(cache_key)
    if cached:
        result = GeoJSONFeatureCollection.model_validate(cached)
    else:
        result = await query_live_events(
            session=session,
            category=category,
            subcategory=subcategory,
            district=district,
            min_severity=min_severity,
            active_only=active_only,
            bbox=bbox,
            limit=limit,
            offset=offset,
        )
        await set_cached_json(cache_key, result.model_dump(mode="json"), ttl_seconds=10)

    # Compute ETag for efficient frontend map polling
    dumped = result.model_dump_json()
    etag = f'"{hashlib.md5(dumped.encode()).hexdigest()}"'
    response.headers["ETag"] = etag

    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match == etag:
        response.status_code = status.HTTP_304_NOT_MODIFIED
        return GeoJSONFeatureCollection(type="FeatureCollection", features=[])

    return result
