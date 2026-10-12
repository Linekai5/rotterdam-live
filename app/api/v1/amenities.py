"""FastAPI Router for Municipal Civic Amenities and Urban Infrastructure."""
import json
from typing import Optional, Tuple
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, parse_bbox_param
from app.cache.redis_client import get_redis_client
from app.schemas.geojson import GeoJSONFeatureCollection
from app.services.spatial_service import query_city_amenities
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


@router.get("/cameras", response_model=GeoJSONFeatureCollection)
async def get_surveillance_cameras(
    camera_type: Optional[str] = Query(
        None,
        description="Filter by camera type: commercial, surveillance, traffic, skyline_webcam, anpr",
    ),
    district: Optional[str] = Query(None, description="Filter by district"),
    bbox: Optional[str] = Query(None, description="Bounding box: min_lon,min_lat,max_lon,max_lat"),
    limit: int = Query(500, ge=1, le=2500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
):
    """
    Public and commercial outdoor camera infrastructure across Rotterdam:
    Includes commercial company security (retail, banks, ATMs, parking, fuel),
    police surveillance (Art. 151c), RWS traffic cameras, skyline webcams, and ANPR.
    """
    bbox_coords = parse_bbox_param(bbox)
    cache_key = f"amenities:cameras:{camera_type}:{district}:{bbox}:{limit}:{offset}"
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
