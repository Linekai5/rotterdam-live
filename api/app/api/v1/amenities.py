"""FastAPI Router for Municipal Civic Amenities and Urban Infrastructure."""
import json
from typing import Optional, Tuple
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, parse_bbox_param
from app.cache.redis_client import get_redis_client
from app.schemas.geojson import GeoJSONFeatureCollection
from app.services.spatial_service import query_city_amenities, get_camera_statistics
from app.logging import logger

router = APIRouter(prefix="/amenities", tags=["Municipal Amenities"])


@router.get("", response_model=GeoJSONFeatureCollection)
async def get_all_amenities(
    subcategory: Optional[str] = Query(
        None,
        description="Filter by amenity subcategory: toilet, water_tap, ev_charger, camera, aed",
    ),
    district: Optional[str] = Query(None, description="Filter by Rotterdam district"),
    bbox: Optional[str] = Query(
        None, description="Bounding box filter: min_lon,min_lat,max_lon,max_lat"
    ),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    """
    Unified GeoJSON endpoint for all municipal amenities and urban POIs.
    Supports sub-millisecond PostGIS GiST bounding-box filtering and Redis caching.
    """
    bbox_coords = parse_bbox_param(bbox)
    cache_key = f"amenities:all:{subcategory}:{district}:{bbox}:{limit}:{offset}"
    redis = await get_redis_client()

    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return Response(content=cached, media_type="application/json")
        except Exception as e:
            logger.debug("Redis cache read failed: {}", e)

    geojson = await query_city_amenities(
        session=session,
        subcategory=subcategory,
        district=district,
        bbox=bbox_coords,
        limit=limit,
        offset=offset,
    )

    if redis:
        try:
            await redis.setex(cache_key, 3600, geojson.model_dump_json())
        except Exception as e:
            logger.debug("Redis cache write failed: {}", e)

    return geojson


@router.get("/toilets", response_model=GeoJSONFeatureCollection)
async def get_public_toilets(
    wheelchair_accessible: Optional[bool] = Query(
        None, description="Filter for wheelchair / disabled accessible facilities"
    ),
    district: Optional[str] = Query(None, description="Filter by district"),
    bbox: Optional[str] = Query(None, description="Bounding box: min_lon,min_lat,max_lon,max_lat"),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    """
    Official Rotterdam public toilets and urinals from data.rotterdam.nl.
    Includes accessibility details, opening hours, and operator information.
    """
    bbox_coords = parse_bbox_param(bbox)
    cache_key = f"amenities:toilets:{wheelchair_accessible}:{district}:{bbox}:{limit}:{offset}"
    redis = await get_redis_client()

    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return Response(content=cached, media_type="application/json")
        except Exception as e:
            logger.debug("Redis cache read failed: {}", e)

    geojson = await query_city_amenities(
        session=session,
        subcategory="toilet",
        district=district,
        wheelchair_accessible=wheelchair_accessible,
        bbox=bbox_coords,
        limit=limit,
        offset=offset,
    )

    if redis:
        try:
            await redis.setex(cache_key, 7200, geojson.model_dump_json())
        except Exception as e:
            logger.debug("Redis cache write failed: {}", e)

    return geojson


@router.get("/cameras/stats")
async def get_camera_stats(
    session: AsyncSession = Depends(get_db),
):
    """
    Count active mapped camera-location records by category and district.
    These are directory counts, not verified operational-device counts.
    """
    cache_key = "amenities:cameras:stats"
    redis = await get_redis_client()
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return Response(content=cached, media_type="application/json")
        except Exception:
            pass

    stats = await get_camera_statistics(session)
    stats_json = json.dumps(stats)
    if redis:
        try:
            await redis.setex(cache_key, 3600, stats_json)
        except Exception:
            pass

    return Response(content=stats_json, media_type="application/json")


@router.get("/cameras", response_model=GeoJSONFeatureCollection)
async def get_surveillance_cameras(
    camera_type: Optional[str] = Query(
        None,
        description="Filter by category: commercial, surveillance, traffic, anpr, transit, infrastructure, skyline_webcam, general",
    ),
    has_live_feed: Optional[bool] = Query(
        None,
        description="Filter source metadata indicating a public stream/snapshot; availability is not probed here",
    ),
    district: Optional[str] = Query(None, description="Filter by Rotterdam district"),
    bbox: Optional[str] = Query(None, description="Bounding box: min_lon,min_lat,max_lon,max_lat"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    """
    Mapped camera-location directory. An OSM camera tag is not an operational
    check or a promise of public video access; see each record's source metadata.
    Returns an RFC 7946 GeoJSON FeatureCollection using PostGIS bbox filtering and caching.
    If camera_type is omitted, all active mapped camera locations are returned.
    """
    bbox_coords = parse_bbox_param(bbox)
    cache_key = f"amenities:cameras:v2:{camera_type}:{has_live_feed}:{district}:{bbox}:{limit}:{offset}"
    redis = await get_redis_client()

    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return Response(content=cached, media_type="application/json")
        except Exception:
            pass

    geojson = await query_city_amenities(
        session=session,
        subcategory="camera",
        camera_type=camera_type,
        has_live_feed=has_live_feed,
        district=district,
        bbox=bbox_coords,
        limit=limit,
        offset=offset,
    )

    if redis:
        try:
            await redis.setex(cache_key, 7200, geojson.model_dump_json())
        except Exception:
            pass

    return geojson


@router.get("/cameras/live", response_model=GeoJSONFeatureCollection)
async def get_live_viewable_cameras(
    district: Optional[str] = Query(None, description="Filter by district"),
    bbox: Optional[str] = Query(None, description="Bounding box: min_lon,min_lat,max_lon,max_lat"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    """
    Filter records whose source supplies public-footage metadata.
    The current OSM location directory supplies no verified streams, so this
    collection may be empty. External footage is not fetched or checked here.
    """
    bbox_coords = parse_bbox_param(bbox)
    cache_key = f"amenities:cameras:live:v2:{district}:{bbox}:{limit}:{offset}"
    redis = await get_redis_client()

    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return Response(content=cached, media_type="application/json")
        except Exception:
            pass

    geojson = await query_city_amenities(
        session=session,
        subcategory="camera",
        has_live_feed=True,
        district=district,
        bbox=bbox_coords,
        limit=limit,
        offset=offset,
    )

    if redis:
        try:
            await redis.setex(cache_key, 7200, geojson.model_dump_json())
        except Exception:
            pass

    return geojson


@router.get("/cameras/general", response_model=GeoJSONFeatureCollection)
async def get_general_cameras(
    district: Optional[str] = Query(None, description="Filter by district"),
    bbox: Optional[str] = Query(None, description="Bounding box: min_lon,min_lat,max_lon,max_lat"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    """
    General endpoint for unclassified or generic outdoor cameras across Rotterdam.
    """
    bbox_coords = parse_bbox_param(bbox)
    cache_key = f"amenities:cameras:general:{district}:{bbox}:{limit}:{offset}"
    redis = await get_redis_client()

    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return Response(content=cached, media_type="application/json")
        except Exception:
            pass

    geojson = await query_city_amenities(
        session=session,
        subcategory="camera",
        camera_type="general",
        district=district,
        bbox=bbox_coords,
        limit=limit,
        offset=offset,
    )

    if redis:
        try:
            await redis.setex(cache_key, 7200, geojson.model_dump_json())
        except Exception:
            pass

    return geojson


@router.get("/cameras/commercial", response_model=GeoJSONFeatureCollection)
async def get_commercial_cameras(
    district: Optional[str] = Query(None, description="Filter by district"),
    bbox: Optional[str] = Query(None, description="Bounding box: min_lon,min_lat,max_lon,max_lat"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    """
    Legacy commercial-category filter. Venue type alone is not proof of a camera;
    the current OSM directory may return an empty collection for this category.
    """
    return await query_city_amenities(
        session=session,
        subcategory="camera",
        camera_type="commercial",
        district=district,
        bbox=parse_bbox_param(bbox),
        limit=limit,
        offset=offset,
    )


@router.get("/cameras/surveillance", response_model=GeoJSONFeatureCollection)
async def get_police_surveillance_cameras(
    district: Optional[str] = Query(None, description="Filter by district"),
    bbox: Optional[str] = Query(None, description="Bounding box: min_lon,min_lat,max_lon,max_lat"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    """
    Camera locations classified as surveillance by the mapped source.
    This does not establish an operator, legal mandate or current device status.
    """
    return await query_city_amenities(
        session=session,
        subcategory="camera",
        camera_type="surveillance",
        district=district,
        bbox=parse_bbox_param(bbox),
        limit=limit,
        offset=offset,
    )


@router.get("/cameras/transit", response_model=GeoJSONFeatureCollection)
async def get_transit_cameras(
    district: Optional[str] = Query(None, description="Filter by district"),
    bbox: Optional[str] = Query(None, description="Bounding box: min_lon,min_lat,max_lon,max_lat"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    """
    Legacy transit-category filter. A station or access portal alone is not
    proof of a camera, so the current directory may return an empty collection.
    """
    return await query_city_amenities(
        session=session,
        subcategory="camera",
        camera_type="transit",
        district=district,
        bbox=parse_bbox_param(bbox),
        limit=limit,
        offset=offset,
    )


@router.get("/cameras/traffic", response_model=GeoJSONFeatureCollection)
async def get_traffic_monitoring_cameras(
    district: Optional[str] = Query(None, description="Filter by district"),
    bbox: Optional[str] = Query(None, description="Bounding box: min_lon,min_lat,max_lon,max_lat"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    """
    Mapped camera locations classified as traffic-related by their source.
    No public video access or operational status is implied.
    """
    return await query_city_amenities(
        session=session,
        subcategory="camera",
        camera_type="traffic",
        district=district,
        bbox=parse_bbox_param(bbox),
        limit=limit,
        offset=offset,
    )


@router.get("/cameras/anpr", response_model=GeoJSONFeatureCollection)
async def get_anpr_cameras(
    district: Optional[str] = Query(None, description="Filter by district"),
    bbox: Optional[str] = Query(None, description="Bounding box: min_lon,min_lat,max_lon,max_lat"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    """
    Mapped speed/enforcement-camera category. This legacy category name does
    not verify that every recorded device performs number-plate recognition.
    """
    return await query_city_amenities(
        session=session,
        subcategory="camera",
        camera_type="anpr",
        district=district,
        bbox=parse_bbox_param(bbox),
        limit=limit,
        offset=offset,
    )


@router.get("/cameras/infrastructure", response_model=GeoJSONFeatureCollection)
async def get_infrastructure_cameras(
    district: Optional[str] = Query(None, description="Filter by district"),
    bbox: Optional[str] = Query(None, description="Bounding box: min_lon,min_lat,max_lon,max_lat"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    """
    Legacy infrastructure-category filter. A bridge, lock or tunnel alone is
    not proof of a camera, so this collection may be empty.
    """
    return await query_city_amenities(
        session=session,
        subcategory="camera",
        camera_type="infrastructure",
        district=district,
        bbox=parse_bbox_param(bbox),
        limit=limit,
        offset=offset,
    )


@router.get("/water-taps", response_model=GeoJSONFeatureCollection)
async def get_water_taps(
    district: Optional[str] = Query(None, description="Filter by district"),
    bbox: Optional[str] = Query(None, description="Bounding box: min_lon,min_lat,max_lon,max_lat"),
    limit: int = Query(250, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    """
    Public drinking water fountains and tap points (Evides / Gemeente Rotterdam).
    """
    bbox_coords = parse_bbox_param(bbox)
    cache_key = f"amenities:watertaps:{district}:{bbox}:{limit}:{offset}"
    redis = await get_redis_client()

    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return Response(content=cached, media_type="application/json")
        except Exception:
            pass

    geojson = await query_city_amenities(
        session=session,
        subcategory="water_tap",
        district=district,
        bbox=bbox_coords,
        limit=limit,
        offset=offset,
    )

    if redis:
        try:
            await redis.setex(cache_key, 7200, geojson.model_dump_json())
        except Exception:
            pass

    return geojson


@router.get("/ev-chargers", response_model=GeoJSONFeatureCollection)
async def get_ev_chargers(
    district: Optional[str] = Query(None, description="Filter by district"),
    bbox: Optional[str] = Query(None, description="Bounding box: min_lon,min_lat,max_lon,max_lat"),
    limit: int = Query(300, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    """
    Public electric vehicle (EV) charging stations from data.rotterdam.nl.
    """
    bbox_coords = parse_bbox_param(bbox)
    cache_key = f"amenities:evchargers:{district}:{bbox}:{limit}:{offset}"
    redis = await get_redis_client()

    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return Response(content=cached, media_type="application/json")
        except Exception:
            pass

    geojson = await query_city_amenities(
        session=session,
        subcategory="ev_charger",
        district=district,
        bbox=bbox_coords,
        limit=limit,
        offset=offset,
    )

    if redis:
        try:
            await redis.setex(cache_key, 3600, geojson.model_dump_json())
        except Exception:
            pass

    return geojson


@router.get("/aeds", response_model=GeoJSONFeatureCollection)
async def get_aeds(
    district: Optional[str] = Query(None, description="Filter by district"),
    bbox: Optional[str] = Query(None, description="Bounding box: min_lon,min_lat,max_lon,max_lat"),
    limit: int = Query(250, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    """
    Public Automated External Defibrillators (AEDs) for emergency situational awareness.
    """
    bbox_coords = parse_bbox_param(bbox)
    cache_key = f"amenities:aeds:{district}:{bbox}:{limit}:{offset}"
    redis = await get_redis_client()

    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return Response(content=cached, media_type="application/json")
        except Exception:
            pass

    geojson = await query_city_amenities(
        session=session,
        subcategory="aed",
        district=district,
        bbox=bbox_coords,
        limit=limit,
        offset=offset,
    )

    if redis:
        try:
            await redis.setex(cache_key, 7200, geojson.model_dump_json())
        except Exception:
            pass

    return geojson
