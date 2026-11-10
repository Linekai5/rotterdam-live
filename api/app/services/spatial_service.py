"""PostGIS spatial query service with ST_Within district match and ST_Intersects BBOX queries."""
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.logging import logger
from app.schemas.geojson import (
    GeoJSONFeature,
    GeoJSONFeatureCollection,
    PointGeometry,
    PolygonGeometry,
    MultiPolygonGeometry,
    CanonicalEventProperties,
)
from app.config import settings


async def find_district_for_point(
    lon: float, lat: float, session: AsyncSession
) -> Optional[str]:
    """Find Rotterdam district containing (lon, lat) using PostGIS ST_Within."""
    query = text(
        """
        SELECT name 
        FROM rotterdam_districts 
        WHERE ST_Within(
            ST_SetSRID(ST_Point(:lon, :lat), 4326), 
            geom
        )
        LIMIT 1;
        """
    )
    try:
        result = await session.execute(query, {"lon": lon, "lat": lat})
        row = result.fetchone()
        if row:
            return row[0]
    except Exception as e:
        logger.debug("District lookup failed for ({}, {}): {}", lon, lat, e)
    return None


async def upsert_live_event(
    event_data: Dict[str, Any], session: AsyncSession
) -> bool:
    """
    Upsert an event into the live_events table.
    event_data requires:
    id, category, subcategory, severity, timestamp, expires_at, district, title, details, lon, lat (or geometry_geojson)
    """
    stmt = text(
        """
        INSERT INTO live_events (
            id, category, subcategory, severity, timestamp, expires_at, district, title, details, geom, created_at, updated_at
        )
        VALUES (
            :id, :category, :subcategory, :severity, :timestamp, :expires_at, :district, :title, :details,
            ST_SetSRID(ST_Point(:lon, :lat), 4326),
            NOW(),
            NOW()
        )
        ON CONFLICT (id) DO UPDATE SET
            category = EXCLUDED.category,
            subcategory = EXCLUDED.subcategory,
            severity = EXCLUDED.severity,
            timestamp = EXCLUDED.timestamp,
            expires_at = EXCLUDED.expires_at,
            district = COALESCE(EXCLUDED.district, live_events.district),
            title = EXCLUDED.title,
            details = EXCLUDED.details,
            geom = EXCLUDED.geom,
            updated_at = NOW();
        """
    )
    try:
        await session.execute(
            stmt,
            {
                "id": event_data["id"],
                "category": event_data["category"],
                "subcategory": event_data["subcategory"],
                "severity": event_data.get("severity", 1),
                "timestamp": event_data["timestamp"],
                "expires_at": event_data.get("expires_at"),
                "district": event_data.get("district"),
                "title": event_data["title"],
                "details": json.dumps(event_data.get("details", {})),
                "lon": event_data["lon"],
                "lat": event_data["lat"],
            },
        )
        await session.commit()
        return True
    except Exception as e:
        await session.rollback()
        logger.error("Failed to upsert live event {}: {}", event_data.get("id"), e)
        return False


async def query_live_events(
    session: AsyncSession,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    district: Optional[str] = None,
    min_severity: Optional[int] = None,
    active_only: bool = True,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    limit: int = 100,
    offset: int = 0,
) -> GeoJSONFeatureCollection:
    """
    Fast query returning canonical GeoJSON FeatureCollection.
    BBOX format: (min_lon, min_lat, max_lon, max_lat).
    Leverages ST_AsGeoJSON for maximum serialization performance (<30ms).
    """
    conditions = []
    params: Dict[str, Any] = {"limit": limit, "offset": offset}

    if category:
        conditions.append("category = :category")
        params["category"] = category

    if subcategory:
        conditions.append("subcategory = :subcategory")
        params["subcategory"] = subcategory

    if district:
        conditions.append("district = :district")
        params["district"] = district

    if min_severity is not None:
        conditions.append("severity >= :min_severity")
        params["min_severity"] = min_severity

    if active_only:
        if category == "event":
            conditions.append(
                "timestamp <= NOW() AND COALESCE(expires_at, timestamp + INTERVAL '3 hours') >= NOW()"
            )
        elif category:
            conditions.append("(expires_at IS NULL OR expires_at > NOW())")
        else:
            conditions.append(
                "((category != 'event' AND (expires_at IS NULL OR expires_at > NOW())) OR "
                "(category = 'event' AND timestamp <= NOW() AND COALESCE(expires_at, timestamp + INTERVAL '3 hours') >= NOW()))"
            )

    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox
        conditions.append(
            "ST_Intersects(geom, ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326))"
        )
        params["min_lon"] = min_lon
        params["min_lat"] = min_lat
        params["max_lon"] = max_lon
        params["max_lat"] = max_lat

    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

    query = text(
        f"""
        SELECT 
            id,
            category,
            subcategory,
            severity,
            timestamp,
            expires_at,
            district,
            title,
            details,
            ST_AsGeoJSON(geom) as geom_json
        FROM live_events
        {where_clause}
        ORDER BY timestamp DESC
        LIMIT :limit OFFSET :offset;
        """
    )

    result = await session.execute(query, params)
    rows = result.fetchall()

    features: List[GeoJSONFeature] = []
    for row in rows:
        (
            ev_id,
            cat,
            subcat,
            sev,
            ts,
            exp,
            dist,
            ttl,
            dtl,
            geom_json_str,
        ) = row

        geom_dict = json.loads(geom_json_str) if geom_json_str else None
        if not geom_dict:
            continue

        geometry: PointGeometry
        if geom_dict.get("type") == "Point":
            geometry = PointGeometry(
                type="Point", coordinates=geom_dict.get("coordinates", [])
            )
        else:
            # Fallback
            coords = geom_dict.get("coordinates", [])
            geometry = PointGeometry(
                type="Point",
                coordinates=[coords[0], coords[1]] if coords else [settings.ROTTERDAM_CENTER_LON, settings.ROTTERDAM_CENTER_LAT],
            )

        details_dict = dtl if isinstance(dtl, dict) else json.loads(dtl or "{}")

        properties = CanonicalEventProperties(
            id=ev_id,
            category=cat,
            subcategory=subcat,
            severity=sev,
            timestamp=ts,
            expires_at=exp,
            district=dist,
            title=ttl,
            details=details_dict,
        )

        features.append(GeoJSONFeature(type="Feature", geometry=geometry, properties=properties))

    return GeoJSONFeatureCollection(
        type="FeatureCollection",
        features=features,
        total_count=len(features),
    )


async def upsert_city_amenity(
    amenity_data: Dict[str, Any], session: AsyncSession
) -> bool:
    """
    Upsert a municipal amenity or POI into the city_amenities table.
    amenity_data requires:
    id, category, subcategory, name, description, district, details, lon, lat
    """
    stmt = text(
        """
        INSERT INTO city_amenities (
            id, category, subcategory, name, description, district, details, geom, is_active, created_at, updated_at
        )
        VALUES (
            :id, :category, :subcategory, :name, :description, :district, :details,
            ST_SetSRID(ST_Point(:lon, :lat), 4326),
            :is_active,
            NOW(),
            NOW()
        )
        ON CONFLICT (id) DO UPDATE SET
            category = EXCLUDED.category,
            subcategory = EXCLUDED.subcategory,
            name = EXCLUDED.name,
            description = EXCLUDED.description,
            district = COALESCE(EXCLUDED.district, city_amenities.district),
            details = EXCLUDED.details,
            geom = EXCLUDED.geom,
            is_active = EXCLUDED.is_active,
            updated_at = NOW();
        """
    )
    try:
        await session.execute(
            stmt,
            {
                "id": amenity_data["id"],
                "category": amenity_data.get("category", "amenity"),
                "subcategory": amenity_data["subcategory"],
                "name": amenity_data["name"],
                "description": amenity_data.get("description"),
                "district": amenity_data.get("district"),
                "details": json.dumps(amenity_data.get("details", {})),
                "is_active": amenity_data.get("is_active", True),
                "lon": amenity_data["lon"],
                "lat": amenity_data["lat"],
            },
        )
        await session.commit()
        return True
    except Exception as e:
        await session.rollback()
        logger.error("Failed to upsert city amenity {}: {}", amenity_data.get("id"), e)
        return False


async def query_city_amenities(
    session: AsyncSession,
    subcategory: Optional[str] = None,
    district: Optional[str] = None,
    wheelchair_accessible: Optional[bool] = None,
    camera_type: Optional[str] = None,
    has_live_feed: Optional[bool] = None,
    active_only: bool = True,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    limit: int = 200,
    offset: int = 0,
) -> GeoJSONFeatureCollection:
    """
    Fast query returning canonical GeoJSON FeatureCollection for civic amenities.
    BBOX format: (min_lon, min_lat, max_lon, max_lat).
    Uses ST_AsGeoJSON for sub-30ms performance.
    """
    conditions = []
    params: Dict[str, Any] = {"limit": limit, "offset": offset}

    if subcategory:
        conditions.append("subcategory = :subcategory")
        params["subcategory"] = subcategory

    if district:
        conditions.append("district = :district")
        params["district"] = district

    if active_only:
        conditions.append("is_active = true")

    if camera_type:
        if camera_type.lower() == "general":
            conditions.append(
                "(details->>'camera_type' = 'general' OR details->>'camera_type' IS NULL OR "
                "details->>'camera_type' NOT IN ('commercial', 'surveillance', 'traffic', 'anpr', 'transit', 'infrastructure', 'skyline_webcam'))"
            )
        else:
            conditions.append("details->>'camera_type' = :camera_type")
            params["camera_type"] = camera_type

    if has_live_feed is not None:
        # Older records can contain a public URL alongside a false/missing flag.
        # Use one predicate and its inverse so filters cannot overlap, and do
        # not count empty provider URL strings as a viewing link.
        live_feed = (
            "(COALESCE(details->>'has_live_feed' = 'true', FALSE) OR "
            "NULLIF(BTRIM(details->>'snapshot_url'), '') IS NOT NULL OR "
            "NULLIF(BTRIM(details->>'stream_url'), '') IS NOT NULL)"
        )
        conditions.append(live_feed if has_live_feed else f"NOT {live_feed}")

    if wheelchair_accessible is not None:
        if wheelchair_accessible:
            conditions.append("(details->>'wheelchair_accessible' = 'true' OR details->>'rolstoeltoegankelijk' = 'true')")
        else:
            conditions.append("(details->>'wheelchair_accessible' = 'false' OR details->>'rolstoeltoegankelijk' = 'false')")

    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox
        conditions.append(
            "ST_Intersects(geom, ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326))"
        )
        params["min_lon"] = min_lon
        params["min_lat"] = min_lat
        params["max_lon"] = max_lon
        params["max_lat"] = max_lat

    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

    query = text(
        f"""
        SELECT 
            id,
            category,
            subcategory,
            name,
            description,
            district,
            details,
            created_at,
            ST_AsGeoJSON(geom) as geom_json
        FROM city_amenities
        {where_clause}
        ORDER BY name ASC
        LIMIT :limit OFFSET :offset;
        """
    )

    result = await session.execute(query, params)
    rows = result.fetchall()

    features: List[GeoJSONFeature] = []
    for row in rows:
        (
            am_id,
            cat,
            subcat,
            nm,
            desc,
            dist,
            dtl,
            created,
            geom_json_str,
        ) = row

        geom_dict = json.loads(geom_json_str) if geom_json_str else None
        if not geom_dict:
            continue

        geometry = PointGeometry(
            type="Point", coordinates=geom_dict.get("coordinates", [])
        )

        details_dict = dtl if isinstance(dtl, dict) else json.loads(dtl or "{}")

        properties = CanonicalEventProperties(
            id=am_id,
            category=cat,
            subcategory=subcat,
            severity=1,
            timestamp=created,
            expires_at=None,
            district=dist,
            title=nm,
            details=details_dict,
        )

        features.append(GeoJSONFeature(type="Feature", geometry=geometry, properties=properties))
 
    return GeoJSONFeatureCollection(
        type="FeatureCollection",
        features=features,
        total_count=len(features),
    )


async def get_camera_statistics(session: AsyncSession) -> Dict[str, Any]:
    """
    Retrieve aggregated counts of verified cameras across categories and districts in Rotterdam.
    """
    stmt_cat = text("""
        SELECT 
            CASE 
                WHEN details->>'camera_type' IN ('commercial', 'surveillance', 'traffic', 'anpr', 'transit', 'infrastructure', 'skyline_webcam') 
                    THEN details->>'camera_type'
                ELSE 'general'
            END as ctype,
            COUNT(*) as count
        FROM city_amenities
        WHERE subcategory = 'camera' AND is_active = true
        GROUP BY ctype
        ORDER BY count DESC;
    """)
    res_cat = await session.execute(stmt_cat)
    categories = {row[0]: row[1] for row in res_cat.fetchall()}

    stmt_dist = text("""
        SELECT COALESCE(district, 'Onbekend') as dist, COUNT(*) as count
        FROM city_amenities
        WHERE subcategory = 'camera' AND is_active = true
        GROUP BY dist
        ORDER BY count DESC;
    """)
    res_dist = await session.execute(stmt_dist)
    districts = {row[0]: row[1] for row in res_dist.fetchall()}

    total = sum(categories.values())
    return {
        "total_cameras": total,
        "categories": categories,
        "districts": districts,
    }

