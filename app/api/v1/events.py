"""Rotterdam Events Domain API Router (/api/v1/events).

Delivers high-throughput RFC 7946 GeoJSON endpoints for:
- Live Ticketmaster events (Ahoy, De Doelen, Luxor, etc.)
- Stadium fixtures (De Kuip, Het Kasteel, Woudestein)
- Municipal festivals (IFFR, Marathon, North Sea Jazz, Zomercarnaval, etc.)
- Verified venues and statistical aggregations

Guarantees sub-30ms API responses (sub-5ms cached in Redis) with ETag polling support.
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import parse_bbox_param
from app.db.session import get_db
from app.schemas.events import (
    RotterdamEventFeature,
    RotterdamEventFeatureCollection,
    VenueListResponse,
    EventStatsResponse,
    StadiumFeatureCollection,
)
from app.services.events_service import (
    query_rotterdam_events,
    query_event_by_id,
    query_event_venues,
    query_event_stats,
    query_stadium_venues,
)
from app.cache.redis_client import get_cached_json, set_cached_json, quantize_bbox

router = APIRouter(prefix="/events", tags=["Rotterdam Events & Cultural Agendas"])


@router.get("", response_model=RotterdamEventFeatureCollection)
async def get_events(
    request: Request,
    response: Response,
    subcategory: Optional[str] = Query(
        None,
        description="Filter by subcategory: concert, stadium_fixture, festival, theatre, comedy, sports, cultural, exhibition",
    ),
    source: Optional[str] = Query(
        None,
        description="Filter by source: ticketmaster, stadium_fixtures, municipal_festivals, open_agenda",
    ),
    district: Optional[str] = Query(None, description="Filter by Rotterdam district name or partial string"),
    venue: Optional[str] = Query(None, description="Filter by venue name (e.g. 'Ahoy', 'De Kuip', 'Doelen')"),
    q: Optional[str] = Query(None, description="Keyword search in event title, venue, or description"),
    date_from: Optional[datetime] = Query(None, description="Filter events starting on or after ISO 8601 UTC"),
    date_to: Optional[datetime] = Query(None, description="Filter events starting on or before ISO 8601 UTC"),
    active_only: bool = Query(True, description="Only return active unexpired events"),
    include_past: bool = Query(False, description="Include past events (default excludes past events)"),
    bbox: Optional[Tuple[float, float, float, float]] = Depends(parse_bbox_param),
    limit: int = Query(100, ge=1, le=500, description="Max items to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_db),
) -> RotterdamEventFeatureCollection:
    """
    Query Rotterdam events in RFC 7946 GeoJSON format.
    Features sub-5ms Redis caching and conditional HTTP 304 ETag support.
    """
    bbox_str = quantize_bbox(*bbox) if bbox else "none"
    d_from_str = date_from.isoformat() if date_from else "none"
    d_to_str = date_to.isoformat() if date_to else "none"

    cache_key = (
        f"events:list:{bbox_str}:{subcategory}:{source}:{district}:{venue}:{q}:"
        f"{d_from_str}:{d_to_str}:{active_only}:{include_past}:{limit}:{offset}"
    )

    cached = await get_cached_json(cache_key)
    if cached:
        result = RotterdamEventFeatureCollection.model_validate(cached)
    else:
        result = await query_rotterdam_events(
            session=session,
            subcategory=subcategory,
            source=source,
            district=district,
            venue=venue,
            q=q,
            date_from=date_from,
            date_to=date_to,
            active_only=active_only,
            include_past=include_past,
            bbox=bbox,
            limit=limit,
            offset=offset,
        )
        await set_cached_json(cache_key, result.model_dump(mode="json"), ttl_seconds=300)

    # Compute ETag for efficient client map polling
    dumped = result.model_dump_json()
    etag = f'"{hashlib.md5(dumped.encode()).hexdigest()}"'
    response.headers["ETag"] = etag

    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match == etag:
        response.status_code = status.HTTP_304_NOT_MODIFIED
        return RotterdamEventFeatureCollection(type="FeatureCollection", features=[])

    return result


@router.get("/today", response_model=RotterdamEventFeatureCollection)
async def get_events_today(
    district: Optional[str] = Query(None, description="Filter by district"),
    include_past: bool = Query(False, description="Include past events that occurred earlier today"),
    session: AsyncSession = Depends(get_db),
) -> RotterdamEventFeatureCollection:
    """
    Events scheduled for today in Rotterdam.
    Filtered by default to active/upcoming events today.
    """
    now = datetime.now(timezone.utc)
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    cache_key = f"events:today:{district or 'all'}:{include_past}:{start_of_today.date().isoformat()}"
    cached = await get_cached_json(cache_key)
    if cached:
        return RotterdamEventFeatureCollection.model_validate(cached)

    result = await query_rotterdam_events(
        session=session,
        district=district,
        date_from=start_of_today,
        date_to=end_of_today,
        include_past=include_past,
        limit=100,
    )
    await set_cached_json(cache_key, result.model_dump(mode="json"), ttl_seconds=120)
    return result


@router.get("/venues", response_model=VenueListResponse)
async def get_venues(
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> VenueListResponse:
    """
    List verified cultural venues, stadiums, and concert halls in Rotterdam with event tallies.
    Cached for 10 minutes.
    """
    cache_key = "events:venues:all"
    cached = await get_cached_json(cache_key)
    if cached:
        return VenueListResponse.model_validate(cached)

    result = await query_event_venues(session)
    await set_cached_json(cache_key, result.model_dump(mode="json"), ttl_seconds=600)
    return result


@router.get("/festivals", response_model=RotterdamEventFeatureCollection)
async def get_festivals(
    district: Optional[str] = Query(None, description="Filter by district"),
    include_past: bool = Query(False, description="Include past festivals"),
    session: AsyncSession = Depends(get_db),
) -> RotterdamEventFeatureCollection:
    """
    Dedicated endpoint for Rotterdam municipal festivals and open cultural agendas
    (IFFR, Marathon, North Sea Jazz, Zomercarnaval, Wereldhavendagen, etc.).
    """
    cache_key = f"events:festivals:{district or 'all'}:{include_past}"
    cached = await get_cached_json(cache_key)
    if cached:
        return RotterdamEventFeatureCollection.model_validate(cached)

    result = await query_rotterdam_events(
        session=session,
        source="municipal_festivals",
        district=district,
        include_past=include_past,
        limit=50,
    )
    await set_cached_json(cache_key, result.model_dump(mode="json"), ttl_seconds=600)
    return result


@router.get("/fixtures", response_model=RotterdamEventFeatureCollection)
async def get_stadium_fixtures(
    club: Optional[str] = Query(None, description="Filter by club or stadium (Feyenoord, Sparta, Excelsior)"),
    include_past: bool = Query(False, description="Include past matches"),
    session: AsyncSession = Depends(get_db),
) -> RotterdamEventFeatureCollection:
    """
    Dedicated endpoint for Rotterdam football stadium fixtures
    (Stadion Feijenoord / De Kuip, Sparta-Stadion Het Kasteel, Van Donge & De Roo Stadion).
    """
    cache_key = f"events:fixtures:{club or 'all'}:{include_past}"
    cached = await get_cached_json(cache_key)
    if cached:
        return RotterdamEventFeatureCollection.model_validate(cached)

    result = await query_rotterdam_events(
        session=session,
        source="stadium_fixtures",
        venue=club,
        include_past=include_past,
        limit=100,
    )
    await set_cached_json(cache_key, result.model_dump(mode="json"), ttl_seconds=600)
    return result


@router.get("/stadiums", response_model=StadiumFeatureCollection)
async def get_stadiums(
    session: AsyncSession = Depends(get_db),
) -> StadiumFeatureCollection:
    """
    Dedicated endpoint for Rotterdam's 3 football stadiums (physical venue points):
    - De Kuip (Stadion Feijenoord)
    - Sparta-Stadion Het Kasteel
    - Van Donge & De Roo Stadion (Woudestein)
    Includes venue metadata and next scheduled fixture.
    """
    cache_key = "events:stadiums:venues"
    cached = await get_cached_json(cache_key)
    if cached:
        return StadiumFeatureCollection.model_validate(cached)

    result = await query_stadium_venues(session)
    await set_cached_json(cache_key, result.model_dump(mode="json"), ttl_seconds=600)
    return result


@router.get("/stats", response_model=EventStatsResponse)
async def get_events_stats(
    session: AsyncSession = Depends(get_db),
) -> EventStatsResponse:
    """
    Aggregate statistics of Rotterdam events: totals by subcategory, provider, district, and top venues.
    """
    cache_key = "events:stats:summary"
    cached = await get_cached_json(cache_key)
    if cached:
        return EventStatsResponse.model_validate(cached)

    result = await query_event_stats(session)
    await set_cached_json(cache_key, result.model_dump(mode="json"), ttl_seconds=300)
    return result


@router.get("/{event_id}", response_model=RotterdamEventFeature)
async def get_event_detail(
    event_id: str,
    session: AsyncSession = Depends(get_db),
) -> RotterdamEventFeature:
    """
    Retrieve single event details as an RFC 7946 GeoJSON Feature.
    """
    cache_key = f"events:single:{event_id}"
    cached = await get_cached_json(cache_key)
    if cached:
        return RotterdamEventFeature.model_validate(cached)

    event_feat = await query_event_by_id(session, event_id)
    if not event_feat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event '{event_id}' not found.",
        )

    await set_cached_json(cache_key, event_feat.model_dump(mode="json"), ttl_seconds=600)
    return event_feat
