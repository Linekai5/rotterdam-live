"""OSM camera-location directory; never infer devices or invent public streams.

Only explicit camera/surveillance/speed-camera tags establish a mapped location.
A location record is not an operational check or a publicly viewable video feed.
"""
from typing import Any, Dict, Optional

from sqlalchemy import text

from app.cache.redis_client import get_redis_client
from app.db.session import AsyncSessionLocal
from app.ingestion.base import BaseIngestor
from app.logging import logger
from app.services.spatial_service import find_district_for_point, upsert_city_amenity


def camera_record_from_osm(node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize an explicitly tagged OSM node without inferring a camera at a venue."""
    tags = node.get("tags", {})
    tagged = (
        tags.get("man_made") in {"surveillance", "speed_trap"}
        or tags.get("highway") == "speed_camera"
        or any(tags.get(key) not in (None, "", "no", "false") for key in
               ("surveillance", "camera:type", "surveillance:type"))
        or tags.get("cctv") == "yes"
    )
    if not tagged or node.get("type", "node") != "node":
        return None
    if tags.get("indoor") in {"yes", "true"} or tags.get("location") == "indoor":
        return None
    osm_id = str(node.get("id", ""))
    if not osm_id.isdigit():
        return None
    try:
        lon, lat = float(node["lon"]), float(node["lat"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        return None

    device_type = tags.get("surveillance:type") or tags.get("camera:type")
    camera_type = "anpr" if tags.get("highway") == "speed_camera" or tags.get("man_made") == "speed_trap" else "surveillance"
    if tags.get("surveillance:zone") == "traffic":
        camera_type = "traffic"
    source_url = f"https://www.openstreetmap.org/node/{osm_id}"
    return {
        "id": f"camera-{osm_id}", "category": "amenity", "subcategory": "camera",
        "name": tags.get("name") or "Mapped camera location",
        "description": "Camera location recorded in OpenStreetMap. Public footage and operational status are not verified.",
        "lon": lon, "lat": lat, "is_active": True,
        "details": {
            "osm_id": osm_id, "camera_type": camera_type, "device_type": device_type,
            "operator": tags.get("operator"), "surveillance_zone": tags.get("surveillance:zone"),
            "source": "OpenStreetMap", "source_url": source_url,
            "location_basis": "osm_camera_tag", "feed_status": "not_provided",
            "has_live_feed": False, "stream_url": None, "snapshot_url": None,
            "source_updated_at": node.get("timestamp"),
        },
    }


async def retire_unsupported_camera_records(session) -> int:
    """Retire only the old camera engine's inferred/duplicate rows and synthetic fallbacks.

    Keep source-tagged OSM records. No physical camera is deleted or considered
    removed in the real world; inactive rows remain in the database for audit.
    """
    result = await session.execute(text("""
        UPDATE city_amenities SET is_active = FALSE, updated_at = NOW()
        WHERE subcategory = 'camera' AND is_active AND (
            (details->>'source' = 'Rotterdam Camera Engine' AND (
                COALESCE(details->>'venue_type', '') NOT IN ('public_security', 'speed_enforcement')
                OR COALESCE(details->>'osm_id', '') !~ '^[n]?[0-9]+$'
            ))
            OR id LIKE 'camera-cam-%'
        )
    """))
    retired = result.rowcount
    # Repair known legacy OSM metadata without pretending it was newly observed.
    await session.execute(text("""
        UPDATE city_amenities SET
            details = (details - 'stream_url' - 'snapshot_url') || jsonb_build_object(
                'source', 'OpenStreetMap',
                'source_url', 'https://www.openstreetmap.org/node/' || regexp_replace(details->>'osm_id', '^n', ''),
                'location_basis', 'osm_camera_tag', 'feed_status', 'not_provided', 'has_live_feed', FALSE,
                'device_type', details->>'camera_type',
                'camera_type', CASE
                    WHEN details->>'venue_type' = 'speed_enforcement' THEN 'anpr'
                    WHEN details->>'camera_type' IN ('surveillance', 'traffic', 'anpr') THEN details->>'camera_type'
                    WHEN details->>'surveillance_zone' = 'traffic' THEN 'traffic'
                    ELSE 'surveillance'
                END),
            description = 'Camera location recorded in OpenStreetMap. Public footage and operational status are not verified.'
        WHERE subcategory = 'camera' AND is_active
            AND details->>'osm_id' ~ '^[n]?[0-9]+$'
            AND (details->>'source' = 'Rotterdam Camera Engine' OR details->>'source' IS NULL)
    """))
    duplicates = await session.execute(text("""
        UPDATE city_amenities AS duplicate SET is_active = FALSE, updated_at = NOW()
        WHERE duplicate.subcategory = 'camera' AND duplicate.is_active AND duplicate.id LIKE 'cam-osm-%'
            AND EXISTS (SELECT 1 FROM city_amenities AS original
                WHERE original.id = 'camera-' || regexp_replace(duplicate.details->>'osm_id', '^n', '')
                    AND original.subcategory = 'camera' AND original.is_active)
    """))
    return retired + duplicates.rowcount


class RotterdamCameraHarvester(BaseIngestor):
    """Refresh a directory from actual OSM tags. Provider failure retains prior records."""
    OVERPASS_MIRRORS = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]
    QUERY = '''[out:json][timeout:20];
        area["name"="Rotterdam"]["admin_level"="8"][boundary=administrative]->.a;
        (node["man_made"="surveillance"](area.a); node["surveillance"](area.a);
         node["highway"="speed_camera"](area.a); node["man_made"="speed_trap"](area.a);
         node["camera:type"](area.a); node["surveillance:type"](area.a); node["cctv"="yes"](area.a););
        out meta;'''

    def __init__(self):
        super().__init__(name="rotterdam_camera_harvester", timeout_seconds=25.0)

    async def fetch_nodes(self):
        client = await self.get_client()
        for url in self.OVERPASS_MIRRORS:
            try:
                response = await client.get(url, params={"data": self.QUERY})
                response.raise_for_status()
                nodes = response.json().get("elements")
                if isinstance(nodes, list):
                    return nodes
            except Exception as error:
                logger.warning("Camera directory source unavailable at {}: {}", url, error)
        return None

    async def ingest(self) -> Dict[str, Any]:
        async with AsyncSessionLocal() as session:
            retired = await retire_unsupported_camera_records(session)
            await session.commit()
        nodes = await self.fetch_nodes()
        saved = 0
        if nodes is not None:
            async with AsyncSessionLocal() as session:
                for node in nodes:
                    record = camera_record_from_osm(node)
                    if not record:
                        continue
                    district = await find_district_for_point(record["lon"], record["lat"], session)
                    if not district:
                        continue
                    record["district"] = district
                    if await upsert_city_amenity(record, session):
                        saved += 1
                retired += await retire_unsupported_camera_records(session)
                await session.commit()
        # Invalidate directory snapshots in the worker, never in a client request.
        await invalidate_camera_cache()
        logger.info("OSM camera directory: {} refreshed, {} unsupported/duplicate records retired", saved, retired)
        return {"total_cameras": saved, "retired_unsupported": retired, "source_available": nodes is not None}


async def invalidate_camera_cache():
    try:
        redis = await get_redis_client()
        if redis:
            for pattern in ("amenities:cameras*", "amenities:all:*"):
                keys = [key async for key in redis.scan_iter(match=pattern, count=100)]
                if keys:
                    await redis.delete(*keys)
    except Exception as error:
        logger.warning("Camera directory cache invalidation failed: {}", error)
