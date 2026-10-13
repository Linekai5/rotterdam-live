"""Geospatial Baselines API router (/api/v1/spatial)."""
import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.cache.redis_client import get_cached_json, set_cached_json

router = APIRouter(prefix="/spatial", tags=["Geospatial Baselines"])


@router.get("/districts")
async def get_rotterdam_districts(
    district_type: Optional[str] = Query(
        "wijk", description="Filter by type: wijk or buurt"
    ),
    name: Optional[str] = Query(
        None, description="Filter by specific district name"
    ),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get official Gemeente Rotterdam district & neighborhood polygon boundaries (WGS84 EPSG:4326).
    Designed for Svelte vector-tile map layers and ST_Within association.
    """
    cache_key = f"spatial:districts:{district_type}:{name}"
    cached = await get_cached_json(cache_key)
    if cached:
        return cached

    conditions = []
    params: Dict[str, Any] = {}

    if district_type:
        conditions.append("district_type = :district_type")
        params["district_type"] = district_type

    if name:
        conditions.append("name ILIKE :name")
        params["name"] = f"%{name}%"

    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

    query = text(
        f"""
        SELECT 
            id,
            code,
            name,
            district_type,
            properties,
            ST_AsGeoJSON(geom) as geom_json
        FROM rotterdam_districts
        {where_clause}
        ORDER BY name ASC;
        """
    )

    result = await session.execute(query, params)
    rows = result.fetchall()

    features = []
    for row in rows:
        d_id, code, d_name, d_type, props, geom_str = row
        geom = json.loads(geom_str) if geom_str else None
        if not geom:
            continue

        prop_dict = props if isinstance(props, dict) else json.loads(props or "{}")
        prop_dict["id"] = d_id
        prop_dict["code"] = code
        prop_dict["name"] = d_name
        prop_dict["district_type"] = d_type

        features.append(
            {
                "type": "Feature",
                "id": code,
                "geometry": geom,
                "properties": prop_dict,
            }
        )

    geojson_response = {
        "type": "FeatureCollection",
        "features": features,
        "total_count": len(features),
    }

    await set_cached_json(cache_key, geojson_response, ttl_seconds=3600)
    return geojson_response
