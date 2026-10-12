"""Rotterdam Retail Infrastructure Harvester.

Extracts, validates, and harmonizes every commercial shop, supermarket, and retail facility
across Rotterdam using our C++ Osmium toolchain and Geofabrik Zuid-Holland OpenStreetMap PBF extracts.
Enforces strict spatial validation against PostGIS rotterdam_districts and links each venue
to its official Kadaster BAG address (bag_address_id) and building (bag_pand_id).
"""
import json
import os
import subprocess
import time
from typing import Any, Dict, List, Optional
import shapely.geometry
from sqlalchemy import text
from app.ingestion.base import BaseIngestor
from app.logging import logger
from app.db.session import engine
from app.cache.redis_client import get_redis_client


class RotterdamRetailHarvester(BaseIngestor):
    """Harvester for verified commercial shops, supermarkets, and retail facilities in Rotterdam."""

    DEFAULT_PBF_PATH = "data/zuid-holland.osm.pbf"
    EXTRACTED_GEOJSON_PATH = "data/retail_zh.geojson"
    EXTRACTED_PBF_PATH = "data/retail_zh.osm.pbf"

    def __init__(self):
        super().__init__(name="rotterdam_retail_harvester", timeout_seconds=30.0)

    def ensure_osm_extract(self) -> str:
        """Ensure filtered retail GeoJSON extract exists; run Osmium if needed."""
        if os.path.exists(self.EXTRACTED_GEOJSON_PATH):
            logger.info("Using existing retail GeoJSON extract: {}", self.EXTRACTED_GEOJSON_PATH)
            return self.EXTRACTED_GEOJSON_PATH

        if not os.path.exists(self.DEFAULT_PBF_PATH):
            raise FileNotFoundError(f"Source OSM PBF not found at {self.DEFAULT_PBF_PATH}")

        logger.info("Extracting retail facilities from {} using Osmium toolchain...", self.DEFAULT_PBF_PATH)
        # 1. Filter tags
        cmd_filter = [
            "osmium", "tags-filter", self.DEFAULT_PBF_PATH,
            "nwr/shop", "nwr/amenity=marketplace,pharmacy",
            "-o", self.EXTRACTED_PBF_PATH, "--overwrite"
        ]
        res1 = subprocess.run(cmd_filter, capture_output=True, text=True)
        if res1.returncode != 0:
            logger.error("Osmium tags-filter failed: {}", res1.stderr)
            raise RuntimeError(f"Osmium filter failed: {res1.stderr}")

        # 2. Export to GeoJSON
        cmd_export = [
            "osmium", "export", self.EXTRACTED_PBF_PATH,
            "-o", self.EXTRACTED_GEOJSON_PATH, "--overwrite"
        ]
        res2 = subprocess.run(cmd_export, capture_output=True, text=True)
        if res2.returncode != 0:
            logger.error("Osmium export failed: {}", res2.stderr)
            raise RuntimeError(f"Osmium export failed: {res2.stderr}")

        logger.info("Successfully generated retail GeoJSON extract: {}", self.EXTRACTED_GEOJSON_PATH)
        return self.EXTRACTED_GEOJSON_PATH

    @staticmethod
    def _normalize_shop_type(props: Dict[str, Any]) -> str:
        """Classify and normalize retail venue type."""
        shop = props.get("shop")
        amenity = props.get("amenity")

        if amenity == "pharmacy":
            return "pharmacy"
        if amenity == "marketplace":
            return "marketplace"

        if not shop:
            return "general_retail"

        shop_lower = str(shop).lower().strip()
        common_types = {
            "supermarket": "supermarket",
            "convenience": "convenience",
            "bakery": "bakery",
            "butcher": "butcher",
            "clothes": "clothes",
            "fashion": "clothes",
            "apparel": "clothes",
            "department_store": "department_store",
            "mall": "department_store",
            "electronics": "electronics",
            "chemist": "chemist",
            "shoes": "shoes",
            "books": "books",
            "jewelry": "jewelry",
            "optician": "optician",
            "florist": "florist",
            "sports": "sports",
            "furniture": "furniture",
            "hardware": "hardware",
            "doityourself": "hardware",
            "alcohol": "beverages",
            "beverages": "beverages",
            "wine": "beverages",
            "bicycle": "bicycle",
            "car": "automotive",
            "car_repair": "automotive",
            "hairdresser": "beauty_hair",
            "beauty": "beauty_hair",
            "kiosk": "kiosk",
            "tobacco": "kiosk",
            "variety_store": "variety_store",
        }
        return common_types.get(shop_lower, shop_lower)

    async def ingest(self) -> Dict[str, Any]:
        """Harvest retail infrastructure, apply spatial filters, and link to BAG."""
        start_time = time.time()
        logger.info("Starting Rotterdam Retail Infrastructure harvesting...")

        geojson_path = self.ensure_osm_extract()

        with open(geojson_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", [])
        logger.info("Loaded {} raw retail features from extract", len(features))

        # First pass: parse coordinates and properties within Rotterdam bounding box
        parsed_items: List[Dict[str, Any]] = []
        for feat in features:
            geom = feat.get("geometry")
            if not geom:
                continue

            gtype = geom.get("type")
            coords = geom.get("coordinates", [])

            if gtype == "Point":
                if not coords or len(coords) < 2:
                    continue
                lon = float(coords[0])
                lat = float(coords[1])
            else:
                try:
                    poly = shapely.geometry.shape(geom)
                    c = poly.centroid
                    lon = float(c.x)
                    lat = float(c.y)
                except Exception:
                    continue

            # Rotterdam boundary box pre-filter
            if not (4.30 <= lon <= 4.65 and 51.85 <= lat <= 52.02):
                continue

            props = feat.get("properties", {})
            name = props.get("name")
            brand = props.get("brand") or props.get("operator")
            shop_type = self._normalize_shop_type(props)

            # If unnamed, fall back to brand or shop type description
            if not name:
                if brand:
                    name = brand
                else:
                    name = f"{shop_type.replace('_', ' ').capitalize()} ({props.get('addr:street', 'Rotterdam')})"

            osm_id = str(feat.get("id", f"{round(lon, 6)}_{round(lat, 6)}"))
            venue_id = f"retail-{osm_id}" if not osm_id.startswith("retail-") else osm_id

            street = props.get("addr:street")
            number = props.get("addr:housenumber")
            postcode = props.get("addr:postcode")
            city = props.get("addr:city") or "Rotterdam"

            if postcode:
                postcode = postcode.strip()
                if len(postcode) == 6 and postcode[:4].isdigit() and postcode[4:].isalpha():
                    postcode = f"{postcode[:4]} {postcode[4:].upper()}"

            opening_hours = props.get("opening_hours")
            phone = props.get("phone") or props.get("contact:phone")
            website = props.get("website") or props.get("contact:website")
            wheelchair = props.get("wheelchair")

            parsed_items.append({
                "id": venue_id,
                "name": name[:256],
                "brand": brand[:256] if brand else None,
                "shop_type": shop_type[:64],
                "street_name": street[:256] if street else None,
                "house_number": str(number)[:32] if number else None,
                "postal_code": postcode[:16] if postcode else None,
                "city": city[:128],
                "opening_hours": opening_hours[:256] if opening_hours else None,
                "phone": phone[:64] if phone else None,
                "website": website[:512] if website else None,
                "wheelchair": wheelchair[:32] if wheelchair else None,
                "details": json.dumps(props),
                "lon": lon,
                "lat": lat,
            })

        logger.info("Found {} candidate retail venues in Rotterdam bbox", len(parsed_items))

        # Batch insert into rotterdam_retail
        insert_sql = text("""
            INSERT INTO rotterdam_retail (
                id, name, brand, shop_type, street_name, house_number, postal_code,
                city, opening_hours, phone, website, wheelchair, details,
                geom, is_active, created_at, updated_at
            ) VALUES (
                :id, :name, :brand, :shop_type, :street_name, :house_number, :postal_code,
                :city, :opening_hours, :phone, :website, :wheelchair, CAST(:details AS jsonb),
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), TRUE, NOW(), NOW()
            )
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                brand = EXCLUDED.brand,
                shop_type = EXCLUDED.shop_type,
                street_name = EXCLUDED.street_name,
                house_number = EXCLUDED.house_number,
                postal_code = EXCLUDED.postal_code,
                city = EXCLUDED.city,
                opening_hours = EXCLUDED.opening_hours,
                phone = EXCLUDED.phone,
                website = EXCLUDED.website,
                wheelchair = EXCLUDED.wheelchair,
                details = EXCLUDED.details,
                geom = EXCLUDED.geom,
                is_active = TRUE,
                updated_at = NOW();
        """)

        async with engine.begin() as conn:
            # Insert in chunks of 500
            for i in range(0, len(parsed_items), 500):
                chunk = parsed_items[i : i + 500]
                await conn.execute(insert_sql, chunk)

            # Spatial validation: assign official district
            logger.info("Assigning districts to retail venues via PostGIS ST_Within...")
            await conn.execute(text("""
                UPDATE rotterdam_retail r
                SET district = d.name
                FROM rotterdam_districts d
                WHERE r.district IS NULL AND ST_Within(r.geom, d.geom);
            """))

            await conn.execute(text("""
                UPDATE rotterdam_retail r
                SET district = d.name
                FROM rotterdam_districts d
                WHERE r.district IS NULL AND ST_Intersects(r.geom, d.geom);
            """))

            # Filter out any venue outside official Rotterdam municipal boundaries
            del_res = await conn.execute(text("""
                DELETE FROM rotterdam_retail
                WHERE district IS NULL;
            """))
            logger.info("Removed {} venues situated outside official Rotterdam districts", del_res.rowcount)

            # Spatial Link to BAG: link each retail venue to nearest BAG address and building (within ~35m: 0.00045 deg)
            logger.info("Spatially linking retail venues to Kadaster BAG buildings and addresses...")
            link_res = await conn.execute(text("""
                UPDATE rotterdam_retail
                SET bag_address_id = a.address_id,
                    bag_pand_id = a.pand_id
                FROM (
                    SELECT DISTINCT ON (r.id) r.id, a.address_id, a.pand_id
                    FROM rotterdam_retail r
                    JOIN rotterdam_addresses a
                      ON ST_DWithin(a.geom, r.geom, 0.00045)
                    WHERE r.bag_address_id IS NULL
                    ORDER BY r.id, ST_Distance(a.geom, r.geom) ASC
                ) a
                WHERE rotterdam_retail.id = a.id;
            """))
            logger.info("Spatially linked {} retail venues to BAG buildings", link_res.rowcount)

            # Get final count and category breakdown
            count_res = await conn.execute(text("SELECT count(*) FROM rotterdam_retail;"))
            total_saved = count_res.scalar()

            cat_res = await conn.execute(text("""
                SELECT shop_type, count(*)
                FROM rotterdam_retail
                GROUP BY shop_type
                ORDER BY count(*) DESC
                LIMIT 15;
            """))
            categories = {row[0]: row[1] for row in cat_res.fetchall()}

        # Flush Redis cache
        try:
            redis = await get_redis_client()
            keys = await redis.keys("retail:*")
            if keys:
                await redis.delete(*keys)
                logger.info("Invalidated {} retail cache keys in Redis", len(keys))
        except Exception as e:
            logger.warning("Redis retail cache invalidation warning: {}", e)

        elapsed = time.time() - start_time
        logger.info(
            "Rotterdam Retail harvesting completed in {:.2f}s: {} verified venues in database",
            elapsed,
            total_saved,
        )

        return {
            "status": "success",
            "total_venues": total_saved,
            "top_categories": categories,
            "elapsed_seconds": round(elapsed, 2),
        }
