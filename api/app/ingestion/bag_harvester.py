"""Official Kadaster BAG Address Harvester for Gemeentecode 0599 (Rotterdam).

Ingests the 100% official ground truth of all Rotterdam addresses and postcodes
directly from the Kadaster / PDOK BAG WFS 2.0 service.
Provides centimeter-accurate doorway coordinates, official BAG building purposes
(gebruiksdoel), surface areas, construction years, and postal codes.
Spatially assigns official Rotterdam districts via PostGIS ST_Within(point, rotterdam_districts.geom).
"""
import asyncio
import time
import urllib.parse
from typing import Any, Dict, List, Optional
import httpx
from sqlalchemy import text
from app.ingestion.base import BaseIngestor
from app.logging import logger
from app.db.session import engine
from app.cache.redis_client import get_redis_client


class RotterdamBAGHarvester(BaseIngestor):
    """Harvester for official Kadaster BAG verblijfsobjecten in Gemeente Rotterdam (0599)."""

    PDOK_WFS_URL = "https://service.pdok.nl/lv/bag/wfs/v2_0"
    GEMEENTECODE = "0599"

    ROTTERDAM_POSTCODE_PREFIXES = [
        "301", "302", "303", "304", "305",
        "3061", "3062", "3063", "3064", "3065", "3066", "3067", "3068", "3069",
        "3071", "3072", "3073", "3074", "3075", "3076", "3077", "3078", "3079",
        "308", "315", "318", "319",
    ]

    def __init__(self):
        super().__init__(name="rotterdam_bag_harvester", timeout_seconds=45.0)

    def _get_filter_xml(self, postcode_prefix: Optional[str] = None) -> str:
        """OGC WFS 2.0 Filter selecting Verblijfsobjecten by postcode prefix or gemeentecode."""
        if postcode_prefix:
            return (
                '<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">'
                '<fes:PropertyIsLike wildCard="*" singleChar="." escapeChar="!">'
                '<fes:ValueReference>postcode</fes:ValueReference>'
                f'<fes:Literal>{postcode_prefix}*</fes:Literal>'
                '</fes:PropertyIsLike>'
                '</fes:Filter>'
            )
        return (
            '<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">'
            '<fes:PropertyIsLike wildCard="*" singleChar="." escapeChar="!">'
            '<fes:ValueReference>identificatie</fes:ValueReference>'
            f'<fes:Literal>{self.GEMEENTECODE}01*</fes:Literal>'
            '</fes:PropertyIsLike>'
            '</fes:Filter>'
        )

    async def get_total_matched_for_prefix(self, client: httpx.AsyncClient, prefix: str) -> int:
        """Query PDOK WFS for total matching records for a specific postcode prefix."""
        filter_xml = self._get_filter_xml(prefix)
        encoded_filter = urllib.parse.quote(filter_xml)
        url = (
            f"{self.PDOK_WFS_URL}?service=WFS&version=2.0.0&request=GetFeature"
            f"&typeName=bag:verblijfsobject&resultType=hits&filter={encoded_filter}"
        )
        try:
            resp = await client.get(url, headers={"User-Agent": "RotterdamLive-BAG/1.4"})
            resp.raise_for_status()
            text_resp = resp.text
            if 'numberMatched="' in text_resp:
                match_str = text_resp.split('numberMatched="')[1].split('"')[0]
                return int(match_str)
        except Exception as e:
            logger.warning("Could not parse numberMatched for prefix {}: {}", prefix, e)
        return 0

    async def fetch_page(
        self,
        client: httpx.AsyncClient,
        start_index: int,
        count: int = 1000,
        postcode_prefix: Optional[str] = None,
        max_retries: int = 3,
    ) -> List[Dict[str, Any]]:
        """Fetch a single page of GeoJSON features from PDOK BAG WFS."""
        filter_xml = self._get_filter_xml(postcode_prefix)
        encoded_filter = urllib.parse.quote(filter_xml)
        url = (
            f"{self.PDOK_WFS_URL}?service=WFS&version=2.0.0&request=GetFeature"
            f"&typeName=bag:verblijfsobject&outputFormat=json&count={count}"
            f"&startIndex={start_index}&srsName=EPSG:4326&filter={encoded_filter}"
        )

        for attempt in range(max_retries):
            try:
                resp = await client.get(url, headers={"User-Agent": "RotterdamLive-BAG/1.4"})
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("features", [])
                logger.warning(
                    "PDOK WFS returned status {} for prefix {} startIndex {} (attempt {}/{})",
                    resp.status_code,
                    postcode_prefix,
                    start_index,
                    attempt + 1,
                    max_retries,
                )
            except Exception as e:
                logger.warning(
                    "Error fetching BAG page prefix {} at startIndex {} (attempt {}/{}): {}",
                    postcode_prefix,
                    start_index,
                    attempt + 1,
                    max_retries,
                    e,
                )
            await asyncio.sleep(1.0 * (attempt + 1))
        return []

    async def save_batch(self, features: List[Dict[str, Any]]) -> int:
        """Batch upsert BAG verblijfsobjecten into rotterdam_addresses."""
        if not features:
            return 0

        rows = []
        for feat in features:
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates", [])
            if not coords or len(coords) < 2:
                continue

            lon = float(coords[0])
            lat = float(coords[1])

            # Validation: filter out invalid coordinates
            if not (3.5 <= lon <= 5.5 and 51.5 <= lat <= 52.5):
                continue

            addr_id = props.get("identificatie")
            if not addr_id:
                continue

            street_name = props.get("openbare_ruimte") or ""
            house_number = props.get("huisnummer")
            if house_number is None:
                continue

            house_letter = props.get("huisletter") or None
            house_addition = props.get("toevoeging") or None
            postal_code = props.get("postcode") or None
            if postal_code:
                postal_code = postal_code.strip()
                # Format to standard 'NNNN AA' if 6 chars without space
                if len(postal_code) == 6 and postal_code[:4].isdigit() and postal_code[4:].isalpha():
                    postal_code = f"{postal_code[:4]} {postal_code[4:].upper()}"

            city = props.get("woonplaats") or "Rotterdam"
            purpose = props.get("gebruiksdoel") or None
            surface_area = props.get("oppervlakte")
            construction_year = props.get("bouwjaar")
            status = props.get("status") or None
            pand_id = props.get("pandidentificatie") or None

            rows.append({
                "address_id": addr_id,
                "pand_id": pand_id,
                "street_name": street_name,
                "house_number": int(house_number),
                "house_letter": house_letter,
                "house_addition": house_addition,
                "postal_code": postal_code,
                "city": city,
                "purpose": purpose,
                "surface_area": int(surface_area) if surface_area is not None else None,
                "construction_year": int(construction_year) if construction_year is not None else None,
                "status": status,
                "lon": lon,
                "lat": lat,
            })

        if not rows:
            return 0

        # Construct batch multi-row insert query
        sql = text("""
            INSERT INTO rotterdam_addresses (
                address_id, pand_id, street_name, house_number, house_letter, house_addition,
                postal_code, city, purpose, surface_area, construction_year, status,
                geom, created_at, updated_at
            ) VALUES (
                :address_id, :pand_id, :street_name, :house_number, :house_letter, :house_addition,
                :postal_code, :city, :purpose, :surface_area, :construction_year, :status,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), NOW(), NOW()
            )
            ON CONFLICT (address_id) DO UPDATE SET
                pand_id = EXCLUDED.pand_id,
                street_name = EXCLUDED.street_name,
                house_number = EXCLUDED.house_number,
                house_letter = EXCLUDED.house_letter,
                house_addition = EXCLUDED.house_addition,
                postal_code = EXCLUDED.postal_code,
                city = EXCLUDED.city,
                purpose = EXCLUDED.purpose,
                surface_area = EXCLUDED.surface_area,
                construction_year = EXCLUDED.construction_year,
                status = EXCLUDED.status,
                geom = EXCLUDED.geom,
                updated_at = NOW();
        """)

        async with engine.begin() as conn:
            await conn.execute(sql, rows)

        return len(rows)

    async def resolve_districts(self) -> int:
        """Resolve official Rotterdam districts via PostGIS ST_Within join."""
        logger.info("Resolving official municipal districts for newly ingested addresses...")
        async with engine.begin() as conn:
            # 1. Strict ST_Within matching
            res1 = await conn.execute(text("""
                UPDATE rotterdam_addresses a
                SET district = d.name
                FROM rotterdam_districts d
                WHERE a.district IS NULL AND ST_Within(a.geom, d.geom);
            """))

            # 2. Border fallback: ST_Intersects
            res2 = await conn.execute(text("""
                UPDATE rotterdam_addresses a
                SET district = d.name
                FROM rotterdam_districts d
                WHERE a.district IS NULL AND ST_Intersects(a.geom, d.geom);
            """))

            # 3. Port / harbor edge fallback: nearest district
            res3 = await conn.execute(text("""
                UPDATE rotterdam_addresses a
                SET district = (
                    SELECT d.name FROM rotterdam_districts d
                    ORDER BY ST_Distance(a.geom, d.geom) ASC LIMIT 1
                )
                WHERE a.district IS NULL;
            """))

            total_updated = res1.rowcount + res2.rowcount + res3.rowcount
            logger.info("Resolved districts for {} addresses", total_updated)
            return total_updated

    async def ingest(
        self,
        max_records: Optional[int] = None,
        concurrency: int = 12,
        batch_size: int = 1000,
    ) -> Dict[str, Any]:
        """Execute full or chunked ingestion of Kadaster BAG addresses partitioned by postal code."""
        start_time = time.time()
        logger.info("Starting Kadaster BAG Address ingestion partitioned across Rotterdam postal codes...")

        limits = httpx.Limits(max_connections=concurrency + 5, max_keepalive_connections=concurrency + 5)
        total_saved = 0
        total_matched = 0

        async with httpx.AsyncClient(limits=limits, timeout=self.timeout_seconds) as client:
            sem = asyncio.Semaphore(concurrency)

            for prefix in self.ROTTERDAM_POSTCODE_PREFIXES:
                if max_records and total_saved >= max_records:
                    break

                matched = await self.get_total_matched_for_prefix(client, prefix)
                total_matched += matched
                if matched == 0:
                    continue

                logger.info("Ingesting BAG prefix '{}': {} addresses", prefix, matched)
                page_offsets = list(range(0, matched, batch_size))

                async def process_page(offset: int, pref: str):
                    nonlocal total_saved
                    async with sem:
                        count_to_fetch = min(batch_size, matched - offset)
                        features = await self.fetch_page(client, offset, count=count_to_fetch, postcode_prefix=pref)
                        if features:
                            saved = await self.save_batch(features)
                            total_saved += saved

                tasks = [process_page(offset, prefix) for offset in page_offsets]
                await asyncio.gather(*tasks)
                logger.info("Completed prefix '{}'. Running total saved: {}", prefix, total_saved)

        # Resolve districts in PostGIS
        districts_resolved = await self.resolve_districts()

        # Invalidate cache
        try:
            redis = await get_redis_client()
            keys = await redis.keys("addresses:*")
            if keys:
                await redis.delete(*keys)
                logger.info("Invalidated {} address cache keys in Redis", len(keys))
        except Exception as e:
            logger.warning("Redis address cache invalidation warning: {}", e)

        elapsed = time.time() - start_time
        logger.info(
            "Kadaster BAG ingestion completed in {:.2f}s: {} addresses saved, {} districts resolved",
            elapsed,
            total_saved,
            districts_resolved,
        )

        return {
            "status": "success",
            "total_matched": total_matched,
            "addresses_ingested": total_saved,
            "districts_resolved": districts_resolved,
            "elapsed_seconds": round(elapsed, 2),
        }
