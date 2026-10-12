"""Unified Global Spatial Search API for Rotterdam Live."""
import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query
from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from app.schemas.geojson import GeoJSONFeature, GeoJSONFeatureCollection, PointGeometry, CanonicalEventProperties
from app.cache.redis_client import get_cached_json, set_cached_json
from app.logging import logger
from datetime import datetime, timezone

router = APIRouter(prefix="/search", tags=["Global Spatial Search"])


@router.get("", response_model=Dict[str, Any])
async def global_spatial_search(
    q: str = Query(..., min_length=2, description="Global search query (e.g. 'Coolsingel 42', 'Albert Heijn', 'Erasmusbrug')"),
    types: str = Query("address,retail,amenity", description="Comma-separated entity types: 'address', 'retail', 'amenity'"),
    limit: int = Query(25, ge=1, le=100, description="Max results to return"),
):
    """
    Unified global spatial search across official BAG addresses, commercial retail venues,
    and civic amenities in Rotterdam with sub-30ms response times.
    """
    query_str = q.strip()
    selected_types = [t.strip().lower() for t in types.split(",")]
    cache_key = f"global:search:{query_str}:{types}:{limit}"

    cached = await get_cached_json(cache_key)
    if cached:
        return cached

    results: List[Dict[str, Any]] = []

    async with AsyncSessionLocal() as session:
        # 1. Search Addresses
        if "address" in selected_types:
            tokens = query_str.split()
            first_token = tokens[0].upper()
            is_pc = len(first_token) in (4, 6, 7) and first_token[:4].isdigit()

            if is_pc and len(tokens) >= 2:
                if len(tokens) == 3 and tokens[1].isalpha() and tokens[2].isdigit():
                    pc_clean = f"{tokens[0]} {tokens[1].upper()}"
                    num = int(tokens[2])
                    sql_addr = text("""
                        SELECT 
                            address_id as id, 'address' as entity_type, street_name, house_number,
                            postal_code, purpose, district, ST_X(geom) as lon, ST_Y(geom) as lat,
                            1.0 as score
                        FROM rotterdam_addresses
                        WHERE postal_code = :pc AND house_number = :num
                        LIMIT :limit;
                    """)
                    addr_params = {"pc": pc_clean, "num": num, "limit": limit}
                else:
                    sql_addr = text("""
                        SELECT 
                            address_id as id, 'address' as entity_type, street_name, house_number,
                            postal_code, purpose, district, ST_X(geom) as lon, ST_Y(geom) as lat,
                            similarity(street_name, :q) as score
                        FROM rotterdam_addresses
                        WHERE street_name % :q OR postal_code ILIKE :q_p
                        ORDER BY score DESC
                        LIMIT :limit;
                    """)
                    addr_params = {"q": query_str, "q_p": f"{query_str}%", "limit": limit}
            else:
                sql_addr = text("""
                    SELECT 
                        address_id as id, 'address' as entity_type, street_name, house_number,
                        postal_code, purpose, district, ST_X(geom) as lon, ST_Y(geom) as lat,
                        similarity(street_name, :q) as score
                    FROM rotterdam_addresses
                    WHERE street_name % :q OR street_name ILIKE :q_p
                    ORDER BY score DESC
                    LIMIT :limit;
                """)
                addr_params = {"q": query_str, "q_p": f"{query_str}%", "limit": limit}

            addr_rows = (await session.execute(sql_addr, addr_params)).fetchall()
            for r in addr_rows:
                title = f"{r.street_name} {r.house_number}"
                if r.postal_code:
                    title += f", {r.postal_code}"
                results.append({
                    "type": "Feature",
                    "id": r.id,
                    "geometry": {"type": "Point", "coordinates": [float(r.lon), float(r.lat)]},
                    "properties": {
                        "id": r.id,
                        "entity_type": "address",
                        "title": title,
                        "subtitle": f"{r.district or 'Rotterdam'} • {r.purpose or 'Woonadres'}",
                        "district": r.district,
                        "purpose": r.purpose,
                        "score": float(r.score) if r.score is not None else 0.5,
                    },
                })

        # 2. Search Retail Facilities
        if "retail" in selected_types:
            sql_retail = text("""
                SELECT 
                    id, 'retail' as entity_type, name, brand, shop_type, street_name, house_number,
                    district, bag_address_id, opening_hours, ST_X(geom) as lon, ST_Y(geom) as lat,
                    similarity(name, :q) as score
                FROM rotterdam_retail
                WHERE name % :q OR name ILIKE :q_p OR brand ILIKE :q_p OR shop_type ILIKE :q_p
                ORDER BY score DESC
                LIMIT :limit;
            """)
            retail_rows = (await session.execute(sql_retail, {"q": query_str, "q_p": f"%{query_str}%", "limit": limit})).fetchall()
            for r in retail_rows:
                loc_str = f"{r.street_name} {r.house_number}".strip() if r.street_name else (r.district or "Rotterdam")
                results.append({
                    "type": "Feature",
                    "id": r.id,
                    "geometry": {"type": "Point", "coordinates": [float(r.lon), float(r.lat)]},
                    "properties": {
                        "id": r.id,
                        "entity_type": "retail",
                        "title": r.name,
                        "subtitle": f"{r.shop_type.capitalize()} • {loc_str}",
                        "brand": r.brand,
                        "shop_type": r.shop_type,
                        "district": r.district,
                        "bag_address_id": r.bag_address_id,
                        "opening_hours": r.opening_hours,
                        "score": float(r.score) if r.score is not None else 0.5,
                    },
                })

        # 3. Search Amenities
        if "amenity" in selected_types:
            sql_amen = text("""
                SELECT 
                    id, 'amenity' as entity_type, name, subcategory, district,
                    ST_X(geom) as lon, ST_Y(geom) as lat
                FROM city_amenities
                WHERE name ILIKE :q_p OR subcategory ILIKE :q_p
                LIMIT :limit;
            """)
            amen_rows = (await session.execute(sql_amen, {"q_p": f"%{query_str}%", "limit": limit})).fetchall()
            for r in amen_rows:
                results.append({
                    "type": "Feature",
                    "id": r.id,
                    "geometry": {"type": "Point", "coordinates": [float(r.lon), float(r.lat)]},
                    "properties": {
                        "id": r.id,
                        "entity_type": "amenity",
                        "title": r.name,
                        "subtitle": f"{r.subcategory.capitalize()} • {r.district or 'Rotterdam'}",
                        "subcategory": r.subcategory,
                        "district": r.district,
                        "score": 0.6,
                    },
                })

    # Sort combined results by score descending
    results.sort(key=lambda x: x["properties"].get("score", 0), reverse=True)
    trimmed_results = results[:limit]

    response = {
        "type": "FeatureCollection",
        "query": query_str,
        "total_results": len(trimmed_results),
        "features": trimmed_results,
    }

    await set_cached_json(cache_key, response, ttl_seconds=300)
    return response
