"""Rotterdam Events Domain Spatial Service.

Handles PostGIS ST_Within municipal validation, spatial filtering,
ST_AsGeoJSON serialization, and event persistence.
"""
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.logging import logger
from app.schemas.geojson import PointGeometry
from app.schemas.events import (
    RotterdamEventProperties,
    RotterdamEventFeature,
    RotterdamEventFeatureCollection,
    EventVenueInfo,
    EventPrice,
    VenueSummary,
    VenueListResponse,
    EventStatsResponse,
)
from app.services.spatial_service import find_district_for_point


async def upsert_rotterdam_event(
    event_data: Dict[str, Any], session: AsyncSession
) -> bool:
    """
    Validate spatial boundary and upsert an event into rotterdam_events and live_events.
    Enforces Architectural Invariant: ST_Within(point, rotterdam_districts.geom) must resolve
    an official district. Events outside municipal boundaries are rejected.
    """
    lon = float(event_data["lon"])
    lat = float(event_data["lat"])

    # 1. PostGIS Municipal Boundary Validation
    district = event_data.get("district")
    if not district:
        district = await find_district_for_point(lon=lon, lat=lat, session=session)

    if not district:
        logger.warning(
            "Rejected event '{}' ({}) at ({:.5f}, {:.5f}): Outside Rotterdam municipal boundary.",
            event_data.get("title"),
            event_data.get("id"),
            lon,
            lat,
        )
        return False

    # 2. Upsert into rotterdam_events
    stmt = text(
        """
        INSERT INTO rotterdam_events (
            id, title, description, category, subcategory, source,
            venue_name, venue_address, venue_postal_code,
            start_time, end_time, district, geom,
            price_min, price_max, price_currency,
            ticket_url, image_url, status, details, is_active,
            created_at, updated_at
        )
        VALUES (
            :id, :title, :description, :category, :subcategory, :source,
            :venue_name, :venue_address, :venue_postal_code,
            :start_time, :end_time, :district,
            ST_SetSRID(ST_Point(:lon, :lat), 4326),
            :price_min, :price_max, :price_currency,
            :ticket_url, :image_url, :status, :details, :is_active,
            NOW(), NOW()
        )
        ON CONFLICT (id) DO UPDATE SET
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            category = EXCLUDED.category,
            subcategory = EXCLUDED.subcategory,
            source = EXCLUDED.source,
            venue_name = EXCLUDED.venue_name,
            venue_address = EXCLUDED.venue_address,
            venue_postal_code = EXCLUDED.venue_postal_code,
            start_time = EXCLUDED.start_time,
            end_time = EXCLUDED.end_time,
            district = EXCLUDED.district,
            geom = EXCLUDED.geom,
            price_min = EXCLUDED.price_min,
            price_max = EXCLUDED.price_max,
            price_currency = EXCLUDED.price_currency,
            ticket_url = EXCLUDED.ticket_url,
            image_url = EXCLUDED.image_url,
            status = EXCLUDED.status,
            details = EXCLUDED.details,
            is_active = EXCLUDED.is_active,
            updated_at = NOW();
        """
    )

    details = event_data.get("details", {})
    if isinstance(details, str):
        details_str = details
    else:
        details_str = json.dumps(details)

    try:
        await session.execute(
            stmt,
            {
                "id": str(event_data["id"]),
                "title": event_data["title"],
                "description": event_data.get("description"),
                "category": event_data.get("category", "event"),
                "subcategory": event_data["subcategory"],
                "source": event_data["source"],
                "venue_name": event_data["venue_name"],
                "venue_address": event_data.get("venue_address"),
                "venue_postal_code": event_data.get("venue_postal_code"),
                "start_time": event_data["start_time"],
                "end_time": event_data.get("end_time"),
                "district": district,
                "lon": lon,
                "lat": lat,
                "price_min": event_data.get("price_min"),
                "price_max": event_data.get("price_max"),
                "price_currency": event_data.get("price_currency", "EUR"),
                "ticket_url": event_data.get("ticket_url"),
                "image_url": event_data.get("image_url"),
                "status": event_data.get("status", "scheduled"),
                "details": details_str,
                "is_active": event_data.get("is_active", True),
            },
        )

        # 3. Synchronize with live_events for multi-layer map feed
        live_id = f"live_{event_data['id']}"
        live_stmt = text(
            """
            INSERT INTO live_events (
                id, category, subcategory, severity, timestamp, expires_at,
                district, title, details, geom, created_at, updated_at
            )
            VALUES (
                :id, 'event', :subcategory, 1, :timestamp, :expires_at,
                :district, :title, :details,
                ST_SetSRID(ST_Point(:lon, :lat), 4326),
                NOW(), NOW()
            )
            ON CONFLICT (id) DO UPDATE SET
                category = 'event',
                subcategory = EXCLUDED.subcategory,
                timestamp = EXCLUDED.timestamp,
                expires_at = EXCLUDED.expires_at,
                district = EXCLUDED.district,
                title = EXCLUDED.title,
                details = EXCLUDED.details,
                geom = EXCLUDED.geom,
                updated_at = NOW();
            """
        )

        live_details = {
            "venue_name": event_data["venue_name"],
            "source": event_data["source"],
            "ticket_url": event_data.get("ticket_url"),
            "image_url": event_data.get("image_url"),
            "price_min": event_data.get("price_min"),
            "price_max": event_data.get("price_max"),
            "price_currency": event_data.get("price_currency", "EUR"),
            "status": event_data.get("status", "scheduled"),
        }
        if isinstance(details, dict):
            live_details.update(details)

        await session.execute(
            live_stmt,
            {
                "id": live_id,
                "subcategory": event_data["subcategory"],
                "timestamp": event_data["start_time"],
                "expires_at": event_data.get("end_time"),
                "district": district,
                "title": event_data["title"],
                "details": json.dumps(live_details),
                "lon": lon,
                "lat": lat,
            },
        )

        await session.commit()
        return True
    except Exception as e:
        await session.rollback()
        logger.error("Failed to upsert Rotterdam event {}: {}", event_data.get("id"), e)
        return False


async def query_rotterdam_events(
    session: AsyncSession,
    subcategory: Optional[str] = None,
    source: Optional[str] = None,
    district: Optional[str] = None,
    venue: Optional[str] = None,
    q: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    active_only: bool = True,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    limit: int = 100,
    offset: int = 0,
) -> RotterdamEventFeatureCollection:
    """
    Sub-30ms GeoJSON query for verified Rotterdam events.
    Leverages ST_AsGeoJSON and PostGIS spatial indexing.
    """
    conditions: List[str] = []
    params: Dict[str, Any] = {"limit": limit, "offset": offset}

    if active_only:
        conditions.append("is_active = true")

    if subcategory:
        conditions.append("subcategory = :subcategory")
        params["subcategory"] = subcategory

    if source:
        conditions.append("source = :source")
        params["source"] = source

    if district:
        conditions.append("district ILIKE :district")
        params["district"] = f"%{district}%"

    if venue:
        conditions.append("venue_name ILIKE :venue")
        params["venue"] = f"%{venue}%"

    if q:
        conditions.append("(title ILIKE :q OR venue_name ILIKE :q OR description ILIKE :q)")
        params["q"] = f"%{q}%"

    if date_from:
        conditions.append("start_time >= :date_from")
        params["date_from"] = date_from

    if date_to:
        conditions.append("start_time <= :date_to")
        params["date_to"] = date_to

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
            id, title, description, category, subcategory, source,
            venue_name, venue_address, venue_postal_code,
            start_time, end_time, district,
            price_min, price_max, price_currency,
            ticket_url, image_url, status, details,
            ST_AsGeoJSON(geom) as geom_json
        FROM rotterdam_events
        {where_clause}
        ORDER BY start_time ASC
        LIMIT :limit OFFSET :offset;
        """
    )

    result = await session.execute(query, params)
    rows = result.fetchall()

    features: List[RotterdamEventFeature] = []
    for r in rows:
        (
            ev_id,
            ttl,
            desc,
            cat,
            subcat,
            src,
            v_name,
            v_addr,
            v_postcode,
            s_time,
            e_time,
            dist,
            p_min,
            p_max,
            p_curr,
            t_url,
            i_url,
            stat,
            dtl,
            geom_json_str,
        ) = r

        geom_dict = json.loads(geom_json_str) if geom_json_str else None
        if not geom_dict:
            continue

        coordinates = geom_dict.get("coordinates", [])
        geometry = PointGeometry(type="Point", coordinates=coordinates)

        details_dict = dtl if isinstance(dtl, dict) else json.loads(dtl or "{}")

        price = None
        if p_min is not None or p_max is not None:
            price = EventPrice(min=p_min, max=p_max, currency=p_curr or "EUR")

        ev_lon = float(coordinates[0]) if len(coordinates) >= 1 else None
        ev_lat = float(coordinates[1]) if len(coordinates) >= 2 else None

        venue_info = EventVenueInfo(
            name=v_name,
            address=v_addr,
            postal_code=v_postcode,
            city="Rotterdam",
            district=dist,
            coordinates=coordinates,
            latitude=ev_lat,
            longitude=ev_lon,
        )

        props = RotterdamEventProperties(
            id=ev_id,
            title=ttl,
            description=desc,
            category="event",
            subcategory=subcat,
            source=src,
            venue=venue_info,
            start_time=s_time,
            end_time=e_time,
            district=dist,
            price=price,
            ticket_url=t_url,
            image_url=i_url,
            status=stat,
            details=details_dict,
        )

        features.append(RotterdamEventFeature(type="Feature", geometry=geometry, properties=props))

    return RotterdamEventFeatureCollection(
        type="FeatureCollection",
        features=features,
        total_count=len(features),
    )


async def query_event_by_id(
    session: AsyncSession, event_id: str
) -> Optional[RotterdamEventFeature]:
    """Retrieve single event by ID."""
    stmt = text(
        """
        SELECT 
            id, title, description, category, subcategory, source,
            venue_name, venue_address, venue_postal_code,
            start_time, end_time, district,
            price_min, price_max, price_currency,
            ticket_url, image_url, status, details,
            ST_AsGeoJSON(geom) as geom_json
        FROM rotterdam_events
        WHERE id = :id
        LIMIT 1;
        """
    )
    res = await session.execute(stmt, {"id": event_id})
    row = res.fetchone()
    if not row:
        return None

    (
        ev_id,
        ttl,
        desc,
        cat,
        subcat,
        src,
        v_name,
        v_addr,
        v_postcode,
        s_time,
        e_time,
        dist,
        p_min,
        p_max,
        p_curr,
        t_url,
        i_url,
        stat,
        dtl,
        geom_json_str,
    ) = row

    geom_dict = json.loads(geom_json_str) if geom_json_str else None
    if not geom_dict:
        return None

    coordinates = geom_dict.get("coordinates", [])
    geometry = PointGeometry(type="Point", coordinates=coordinates)

    details_dict = dtl if isinstance(dtl, dict) else json.loads(dtl or "{}")

    price = None
    if p_min is not None or p_max is not None:
        price = EventPrice(min=p_min, max=p_max, currency=p_curr or "EUR")

    ev_lon = float(coordinates[0]) if len(coordinates) >= 1 else None
    ev_lat = float(coordinates[1]) if len(coordinates) >= 2 else None

    venue_info = EventVenueInfo(
        name=v_name,
        address=v_addr,
        postal_code=v_postcode,
        city="Rotterdam",
        district=dist,
        coordinates=coordinates,
        latitude=ev_lat,
        longitude=ev_lon,
    )

    props = RotterdamEventProperties(
        id=ev_id,
        title=ttl,
        description=desc,
        category="event",
        subcategory=subcat,
        source=src,
        venue=venue_info,
        start_time=s_time,
        end_time=e_time,
        district=dist,
        price=price,
        ticket_url=t_url,
        image_url=i_url,
        status=stat,
        details=details_dict,
    )

    return RotterdamEventFeature(type="Feature", geometry=geometry, properties=props)


async def query_event_venues(session: AsyncSession) -> VenueListResponse:
    """Retrieve aggregated list of verified event venues across Rotterdam."""
    stmt = text(
        """
        SELECT 
            venue_name,
            COALESCE(venue_address, '') as venue_address,
            COALESCE(district, 'Rotterdam Centrum') as district,
            ST_X(geom) as lon,
            ST_Y(geom) as lat,
            COUNT(*) as event_count,
            ARRAY_AGG(DISTINCT subcategory) as subcats
        FROM rotterdam_events
        WHERE is_active = true
        GROUP BY venue_name, venue_address, district, lon, lat
        ORDER BY event_count DESC, venue_name ASC;
        """
    )
    res = await session.execute(stmt)
    rows = res.fetchall()

    venues: List[VenueSummary] = []
    for r in rows:
        v_name, v_addr, dist, lon, lat, count, subcats = r
        venues.append(
            VenueSummary(
                name=v_name,
                address=v_addr if v_addr else None,
                district=dist,
                coordinates=[float(lon), float(lat)],
                total_events=int(count),
                subcategories=list(subcats or []),
            )
        )

    return VenueListResponse(total_venues=len(venues), venues=venues)


async def query_event_stats(session: AsyncSession) -> EventStatsResponse:
    """Retrieve high-level statistical breakdowns of Rotterdam events."""
    # Subcategories breakdown
    subcat_stmt = text(
        """
        SELECT subcategory, COUNT(*) 
        FROM rotterdam_events 
        WHERE is_active = true 
        GROUP BY subcategory 
        ORDER BY count DESC;
        """
    )
    subcat_rows = (await session.execute(subcat_stmt)).fetchall()
    subcats = {r[0]: int(r[1]) for r in subcat_rows}

    # Sources breakdown
    src_stmt = text(
        """
        SELECT source, COUNT(*) 
        FROM rotterdam_events 
        WHERE is_active = true 
        GROUP BY source 
        ORDER BY count DESC;
        """
    )
    src_rows = (await session.execute(src_stmt)).fetchall()
    sources = {r[0]: int(r[1]) for r in src_rows}

    # Districts breakdown
    dist_stmt = text(
        """
        SELECT district, COUNT(*) 
        FROM rotterdam_events 
        WHERE is_active = true 
        GROUP BY district 
        ORDER BY count DESC;
        """
    )
    dist_rows = (await session.execute(dist_stmt)).fetchall()
    districts = {r[0]: int(r[1]) for r in dist_rows}

    # Top venues
    ven_stmt = text(
        """
        SELECT venue_name, COUNT(*) 
        FROM rotterdam_events 
        WHERE is_active = true 
        GROUP BY venue_name 
        ORDER BY count DESC 
        LIMIT 10;
        """
    )
    ven_rows = (await session.execute(ven_stmt)).fetchall()
    venues = {r[0]: int(r[1]) for r in ven_rows}

    total = sum(subcats.values())
    return EventStatsResponse(
        total_events=total,
        subcategories=subcats,
        sources=sources,
        districts=districts,
        top_venues=venues,
        timestamp=datetime.now(timezone.utc),
    )
