"""Official Kadaster BAG Addresses API Endpoints."""
import json
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from app.schemas.addresses import AddressFeature, AddressFeatureCollection, AddressProperties, AddressStats
from app.schemas.geojson import PointGeometry
from app.cache.redis_client import get_cached_json, set_cached_json
from app.logging import logger

router = APIRouter(prefix="/addresses", tags=["Kadaster BAG Addresses"])


@router.get("", response_model=AddressFeatureCollection)
async def get_addresses(
    postal_code: Optional[str] = Query(None, description="Filter by 6-character Dutch postal code (e.g. '3011 AD' or '3011AD')"),
    house_number: Optional[int] = Query(None, description="Filter by exact house number"),
    street_name: Optional[str] = Query(None, description="Filter by street name (exact or prefix)"),
    district: Optional[str] = Query(None, description="Filter by official Rotterdam municipal district"),
    purpose: Optional[str] = Query(None, description="Filter by BAG building purpose (woonfunctie, winkelfunctie, etc.)"),
    bbox: Optional[str] = Query(None, description="Bounding box 'min_lon,min_lat,max_lon,max_lat'"),
    limit: int = Query(100, ge=1, le=2000, description="Max features to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """Retrieve official Kadaster BAG addresses across Rotterdam in GeoJSON format."""
    cache_key = f"addresses:list:{postal_code}:{house_number}:{street_name}:{district}:{purpose}:{bbox}:{limit}:{offset}"
    cached = await get_cached_json(cache_key)
    if cached:
        return cached

    conditions = ["1=1"]
    params = {"limit": limit, "offset": offset}

    if postal_code:
        clean_pc = postal_code.strip()
        if len(clean_pc) == 6 and clean_pc[:4].isdigit() and clean_pc[4:].isalpha():
            clean_pc = f"{clean_pc[:4]} {clean_pc[4:].upper()}"
        conditions.append("postal_code = :postal_code")
        params["postal_code"] = clean_pc

    if house_number is not None:
        conditions.append("house_number = :house_number")
        params["house_number"] = house_number

    if street_name:
        conditions.append("street_name ILIKE :street_name")
        params["street_name"] = f"{street_name.strip()}%"

    if district:
        conditions.append("district ILIKE :district")
        params["district"] = district.strip()

    if purpose:
        conditions.append("purpose ILIKE :purpose")
        params["purpose"] = f"%{purpose.strip()}%"

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
            address_id, pand_id, street_name, house_number, house_letter, house_addition,
            postal_code, city, purpose, surface_area, construction_year, status, district,
            ST_X(geom) as lon, ST_Y(geom) as lat,
            count(*) OVER() as full_count
        FROM rotterdam_addresses
        WHERE {where_clause}
        ORDER BY street_name, house_number, house_letter, house_addition
        LIMIT :limit OFFSET :offset;
    """)

    async with AsyncSessionLocal() as session:
        result = await session.execute(sql, params)
        rows = result.fetchall()

    features = []
    total_count = rows[0].full_count if rows else 0

    for r in rows:
        letter_part = f" {r.house_letter}" if r.house_letter else ""
        add_part = f"-{r.house_addition}" if r.house_addition else ""
        num_str = f"{r.house_number}{letter_part}{add_part}"
        pc_str = f", {r.postal_code}" if r.postal_code else ""
        display_name = f"{r.street_name} {num_str}{pc_str} {r.city}".strip()

        props = AddressProperties(
            address_id=r.address_id,
            pand_id=r.pand_id,
            street_name=r.street_name,
            house_number=r.house_number,
            house_letter=r.house_letter,
            house_addition=r.house_addition,
            postal_code=r.postal_code,
            city=r.city,
            purpose=r.purpose,
            surface_area=r.surface_area,
            construction_year=r.construction_year,
            status=r.status,
            district=r.district,
            display_name=display_name,
        )
        features.append(AddressFeature(
            type="Feature",
            id=r.address_id,
            geometry=PointGeometry(type="Point", coordinates=[float(r.lon), float(r.lat)]),
            properties=props,
        ))

    response_data = AddressFeatureCollection(
        type="FeatureCollection",
        features=features,
        total_count=total_count,
    ).model_dump(mode="json")

    await set_cached_json(cache_key, response_data, ttl_seconds=3600)
    return response_data


@router.get("/search", response_model=AddressFeatureCollection)
async def search_addresses(
    q: str = Query(..., min_length=2, description="Search query: street name, postcode + number, or address string"),
    limit: int = Query(25, ge=1, le=100, description="Max search results"),
):
    """Instant sub-30ms address autocomplete using PostgreSQL pg_trgm and B-Tree indexes."""
    query_str = q.strip()
    cache_key = f"addresses:search:{query_str}:{limit}"

    cached = await get_cached_json(cache_key)
    if cached:
        return cached

    # Check if query starts with a postal code (e.g. '3011 AD 42' or '3011AD 42' or '3011')
    tokens = query_str.split()
    first_token = tokens[0].upper()
    is_pc = (len(first_token) in (4, 6, 7) and first_token[:4].isdigit())

    params = {"q": query_str, "limit": limit}

    if is_pc and len(tokens) >= 2:
        # e.g., '3011 AD 12' or '3011AD 12'
        if len(tokens) == 3 and tokens[1].isalpha() and tokens[2].isdigit():
            pc_clean = f"{tokens[0]} {tokens[1].upper()}"
            num = int(tokens[2])
            sql = text("""
                SELECT 
                    address_id, pand_id, street_name, house_number, house_letter, house_addition,
                    postal_code, city, purpose, surface_area, construction_year, status, district,
                    ST_X(geom) as lon, ST_Y(geom) as lat,
                    1 as score
                FROM rotterdam_addresses
                WHERE postal_code = :pc AND house_number = :num
                LIMIT :limit;
            """)
            params = {"pc": pc_clean, "num": num, "limit": limit}
        elif len(first_token) == 6 and tokens[1].isdigit():
            pc_clean = f"{first_token[:4]} {first_token[4:]}"
            num = int(tokens[1])
            sql = text("""
                SELECT 
                    address_id, pand_id, street_name, house_number, house_letter, house_addition,
                    postal_code, city, purpose, surface_area, construction_year, status, district,
                    ST_X(geom) as lon, ST_Y(geom) as lat,
                    1 as score
                FROM rotterdam_addresses
                WHERE postal_code = :pc AND house_number = :num
                LIMIT :limit;
            """)
            params = {"pc": pc_clean, "num": num, "limit": limit}
        else:
            # Match by street name trigram / prefix
            sql = text("""
                SELECT 
                    address_id, pand_id, street_name, house_number, house_letter, house_addition,
                    postal_code, city, purpose, surface_area, construction_year, status, district,
                    ST_X(geom) as lon, ST_Y(geom) as lat,
                    similarity(street_name, :q) as score
                FROM rotterdam_addresses
                WHERE street_name % :q OR street_name ILIKE :q_prefix OR postal_code ILIKE :q_prefix
                ORDER BY score DESC, street_name, house_number
                LIMIT :limit;
            """)
            params["q_prefix"] = f"{query_str}%"
    else:
        # Standard address search (trigram + prefix)
        sql = text("""
            SELECT 
                address_id, pand_id, street_name, house_number, house_letter, house_addition,
                postal_code, city, purpose, surface_area, construction_year, status, district,
                ST_X(geom) as lon, ST_Y(geom) as lat,
                similarity(street_name, :q) as score
            FROM rotterdam_addresses
            WHERE street_name % :q OR street_name ILIKE :q_prefix
            ORDER BY score DESC, street_name, house_number
            LIMIT :limit;
        """)
        params["q_prefix"] = f"{query_str}%"

    async with AsyncSessionLocal() as session:
        result = await session.execute(sql, params)
        rows = result.fetchall()

    features = []
    for r in rows:
        letter_part = f" {r.house_letter}" if r.house_letter else ""
        add_part = f"-{r.house_addition}" if r.house_addition else ""
        num_str = f"{r.house_number}{letter_part}{add_part}"
        pc_str = f", {r.postal_code}" if r.postal_code else ""
        display_name = f"{r.street_name} {num_str}{pc_str} {r.city}".strip()

        props = AddressProperties(
            address_id=r.address_id,
            pand_id=r.pand_id,
            street_name=r.street_name,
            house_number=r.house_number,
            house_letter=r.house_letter,
            house_addition=r.house_addition,
            postal_code=r.postal_code,
            city=r.city,
            purpose=r.purpose,
            surface_area=r.surface_area,
            construction_year=r.construction_year,
            status=r.status,
            district=r.district,
            display_name=display_name,
        )
        features.append(AddressFeature(
            type="Feature",
            id=r.address_id,
            geometry=PointGeometry(type="Point", coordinates=[float(r.lon), float(r.lat)]),
            properties=props,
        ))

    response_data = AddressFeatureCollection(
        type="FeatureCollection",
        features=features,
        total_count=len(features),
    ).model_dump(mode="json")

    await set_cached_json(cache_key, response_data, ttl_seconds=300)
    return response_data


@router.get("/stats", response_model=AddressStats)
async def get_address_stats():
    """Aggregate statistics of all official BAG addresses in Rotterdam."""
    cache_key = "addresses:stats"
    cached = await get_cached_json(cache_key)
    if cached:
        return cached

    async with AsyncSessionLocal() as session:
        count_res = await session.execute(text("SELECT count(*) FROM rotterdam_addresses;"))
        total = count_res.scalar() or 0

        purpose_res = await session.execute(text("""
            SELECT COALESCE(purpose, 'onbekend'), count(*)
            FROM rotterdam_addresses
            GROUP BY COALESCE(purpose, 'onbekend')
            ORDER BY count(*) DESC;
        """))
        purposes = {row[0]: row[1] for row in purpose_res.fetchall()}

        district_res = await session.execute(text("""
            SELECT COALESCE(district, 'Onbekend'), count(*)
            FROM rotterdam_addresses
            GROUP BY COALESCE(district, 'Onbekend')
            ORDER BY count(*) DESC;
        """))
        districts = {row[0]: row[1] for row in district_res.fetchall()}

    stats = AddressStats(
        total_addresses=total,
        purposes=purposes,
        districts=districts,
    ).model_dump(mode="json")

    await set_cached_json(cache_key, stats, ttl_seconds=3600)
    return stats


@router.get("/{address_id}", response_model=AddressFeature)
async def get_address_by_id(address_id: str):
    """Retrieve a single official Kadaster BAG address by its Verblijfsobject ID."""
    cache_key = f"addresses:single:{address_id}"
    cached = await get_cached_json(cache_key)
    if cached:
        return cached

    sql = text("""
        SELECT 
            address_id, pand_id, street_name, house_number, house_letter, house_addition,
            postal_code, city, purpose, surface_area, construction_year, status, district,
            ST_X(geom) as lon, ST_Y(geom) as lat
        FROM rotterdam_addresses
        WHERE address_id = :address_id;
    """)

    async with AsyncSessionLocal() as session:
        res = await session.execute(sql, {"address_id": address_id})
        r = res.fetchone()

    if not r:
        raise HTTPException(status_code=404, detail=f"BAG address '{address_id}' not found")

    letter_part = f" {r.house_letter}" if r.house_letter else ""
    add_part = f"-{r.house_addition}" if r.house_addition else ""
    num_str = f"{r.house_number}{letter_part}{add_part}"
    pc_str = f", {r.postal_code}" if r.postal_code else ""
    display_name = f"{r.street_name} {num_str}{pc_str} {r.city}".strip()

    feat = AddressFeature(
        type="Feature",
        id=r.address_id,
        geometry=PointGeometry(type="Point", coordinates=[float(r.lon), float(r.lat)]),
        properties=AddressProperties(
            address_id=r.address_id,
            pand_id=r.pand_id,
            street_name=r.street_name,
            house_number=r.house_number,
            house_letter=r.house_letter,
            house_addition=r.house_addition,
            postal_code=r.postal_code,
            city=r.city,
            purpose=r.purpose,
            surface_area=r.surface_area,
            construction_year=r.construction_year,
            status=r.status,
            district=r.district,
            display_name=display_name,
        ),
    ).model_dump(mode="json")

    await set_cached_json(cache_key, feat, ttl_seconds=3600)
    return feat
