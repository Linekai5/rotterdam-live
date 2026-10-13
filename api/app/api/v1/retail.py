"""Rotterdam Retail Infrastructure & Commercial Facilities API Endpoints."""
import json
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from app.schemas.retail import RetailFeature, RetailFeatureCollection, RetailProperties, RetailStats
from app.schemas.geojson import PointGeometry
from app.cache.redis_client import get_cached_json, set_cached_json
from app.logging import logger

router = APIRouter(prefix="/retail", tags=["Retail & Commercial Facilities"])


@router.get("", response_model=RetailFeatureCollection)
async def get_retail_facilities(
    shop_type: Optional[str] = Query(None, description="Filter by retail type (supermarket, clothes, bakery, chemist, etc.)"),
    brand: Optional[str] = Query(None, description="Filter by retail brand (Albert Heijn, Jumbo, HEMA, etc.)"),
    district: Optional[str] = Query(None, description="Filter by Rotterdam district (Centrum, Delfshaven, etc.)"),
    wheelchair: Optional[str] = Query(None, description="Filter by wheelchair accessibility ('yes')"),
    q: Optional[str] = Query(None, description="Text search on store name or brand"),
    bbox: Optional[str] = Query(None, description="Bounding box 'min_lon,min_lat,max_lon,max_lat'"),
    limit: int = Query(100, ge=1, le=2000, description="Max venues to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """Retrieve verified retail shops, supermarkets, and commercial facilities in Rotterdam."""
    cache_key = f"retail:list:{shop_type}:{brand}:{district}:{wheelchair}:{q}:{bbox}:{limit}:{offset}"
    cached = await get_cached_json(cache_key)
    if cached:
        return cached

    conditions = ["is_active = TRUE"]
    params = {"limit": limit, "offset": offset}

    if shop_type:
        conditions.append("shop_type = :shop_type")
        params["shop_type"] = shop_type.lower().strip()

    if brand:
        conditions.append("brand ILIKE :brand")
        params["brand"] = f"%{brand.strip()}%"

    if district:
        conditions.append("district ILIKE :district")
        params["district"] = district.strip()

    if wheelchair:
        conditions.append("wheelchair = :wheelchair")
        params["wheelchair"] = wheelchair.strip()

    if q:
        conditions.append("(name ILIKE :q OR brand ILIKE :q)")
        params["q"] = f"%{q.strip()}%"

    if bbox:
        try:
            min_lon, min_lat, max_lon, max_lat = map(float, bbox.split(","))
            conditions.append("geom && ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)")
            params.update({"min_lon": min_lon, "min_lat": min_lat, "max_lon": max_lon, "max_lat": max_lat})
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid bbox format. Use min_lon,min_lat,max_lon,max_lat")

    where_clause = " AND ".join(conditions)

    sql = text(f"""
        SELECT 
            id, name, brand, shop_type, street_name, house_number, postal_code,
            city, district, bag_address_id, bag_pand_id, opening_hours, phone,
            website, wheelchair, details,
            ST_X(geom) as lon, ST_Y(geom) as lat,
            count(*) OVER() as full_count
        FROM rotterdam_retail
        WHERE {where_clause}
        ORDER BY name ASC
        LIMIT :limit OFFSET :offset;
    """)

    async with AsyncSessionLocal() as session:
        result = await session.execute(sql, params)
        rows = result.fetchall()

    features = []
    total_count = rows[0].full_count if rows else 0

    for r in rows:
        props = RetailProperties(
            id=r.id,
            name=r.name,
            brand=r.brand,
            shop_type=r.shop_type,
            street_name=r.street_name,
            house_number=r.house_number,
            postal_code=r.postal_code,
            city=r.city,
            district=r.district,
            bag_address_id=r.bag_address_id,
            bag_pand_id=r.bag_pand_id,
            opening_hours=r.opening_hours,
            phone=r.phone,
            website=r.website,
            wheelchair=r.wheelchair,
            details=r.details or {},
        )
        features.append(RetailFeature(
            type="Feature",
            id=r.id,
            geometry=PointGeometry(type="Point", coordinates=[float(r.lon), float(r.lat)]),
            properties=props,
        ))

    response_data = RetailFeatureCollection(
        type="FeatureCollection",
        features=features,
        total_count=total_count,
    ).model_dump(mode="json")

    await set_cached_json(cache_key, response_data, ttl_seconds=3600)
    return response_data


@router.get("/supermarkets", response_model=RetailFeatureCollection)
async def get_supermarkets(
    district: Optional[str] = Query(None, description="Filter by Rotterdam district"),
    brand: Optional[str] = Query(None, description="Filter by supermarket chain (Albert Heijn, Jumbo, Dirk, etc.)"),
    limit: int = Query(250, ge=1, le=1000, description="Max supermarkets to return"),
):
    """Convenience endpoint returning all physical supermarkets across Rotterdam."""
    return await get_retail_facilities(
        shop_type="supermarket",
        brand=brand,
        district=district,
        wheelchair=None,
        q=None,
        bbox=None,
        limit=limit,
        offset=0,
    )


@router.get("/stats", response_model=RetailStats)
async def get_retail_stats():
    """Aggregate statistics for Rotterdam retail facilities."""
    cache_key = "retail:stats"
    cached = await get_cached_json(cache_key)
    if cached:
        return cached

    async with AsyncSessionLocal() as session:
        count_res = await session.execute(text("SELECT count(*) FROM rotterdam_retail;"))
        total = count_res.scalar() or 0

        sm_res = await session.execute(text("SELECT count(*) FROM rotterdam_retail WHERE shop_type = 'supermarket';"))
        supermarkets_count = sm_res.scalar() or 0

        bag_res = await session.execute(text("SELECT count(*) FROM rotterdam_retail WHERE bag_address_id IS NOT NULL;"))
        bag_linked_count = bag_res.scalar() or 0

        cat_res = await session.execute(text("""
            SELECT shop_type, count(*)
            FROM rotterdam_retail
            GROUP BY shop_type
            ORDER BY count(*) DESC;
        """))
        categories = {row[0]: row[1] for row in cat_res.fetchall()}

        dist_res = await session.execute(text("""
            SELECT COALESCE(district, 'Onbekend'), count(*)
            FROM rotterdam_retail
            GROUP BY COALESCE(district, 'Onbekend')
            ORDER BY count(*) DESC;
        """))
        districts = {row[0]: row[1] for row in dist_res.fetchall()}

    stats = RetailStats(
        total_venues=total,
        categories=categories,
        districts=districts,
        supermarkets_count=supermarkets_count,
        bag_linked_count=bag_linked_count,
    ).model_dump(mode="json")

    await set_cached_json(cache_key, stats, ttl_seconds=3600)
    return stats


@router.get("/{venue_id}", response_model=RetailFeature)
async def get_retail_by_id(venue_id: str):
    """Retrieve details for a single verified retail facility."""
    cache_key = f"retail:single:{venue_id}"
    cached = await get_cached_json(cache_key)
    if cached:
        return cached

    sql = text("""
        SELECT 
            id, name, brand, shop_type, street_name, house_number, postal_code,
            city, district, bag_address_id, bag_pand_id, opening_hours, phone,
            website, wheelchair, details,
            ST_X(geom) as lon, ST_Y(geom) as lat
        FROM rotterdam_retail
        WHERE id = :id;
    """)

    async with AsyncSessionLocal() as session:
        res = await session.execute(sql, {"id": venue_id})
        r = res.fetchone()

    if not r:
        raise HTTPException(status_code=404, detail=f"Retail venue '{venue_id}' not found")

    props = RetailProperties(
        id=r.id,
        name=r.name,
        brand=r.brand,
        shop_type=r.shop_type,
        street_name=r.street_name,
        house_number=r.house_number,
        postal_code=r.postal_code,
        city=r.city,
        district=r.district,
        bag_address_id=r.bag_address_id,
        bag_pand_id=r.bag_pand_id,
        opening_hours=r.opening_hours,
        phone=r.phone,
        website=r.website,
        wheelchair=r.wheelchair,
        details=r.details or {},
    )
    feat = RetailFeature(
        type="Feature",
        id=r.id,
        geometry=PointGeometry(type="Point", coordinates=[float(r.lon), float(r.lat)]),
        properties=props,
    ).model_dump(mode="json")

    await set_cached_json(cache_key, feat, ttl_seconds=3600)
    return feat
