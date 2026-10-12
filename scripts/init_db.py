"""Database initialization script: activates PostGIS and generates tables."""
import asyncio
from sqlalchemy import text
from app.db.session import engine
from app.db.models import Base
from app.logging import setup_logging, logger
from app.ingestion.spatial_baseline import SpatialBaselineIngestor


async def init_database():
    setup_logging()
    logger.info("Initializing PostgreSQL schema with PostGIS extension...")

    async with engine.begin() as conn:
        # 1. Enable PostGIS and pg_trgm extensions
        logger.info("Ensuring PostGIS and pg_trgm extensions are active...")
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))

        # 2. Create tables
        logger.info("Creating database tables if not exist...")
        await conn.run_sync(Base.metadata.create_all)

        # 3. Ensure spatial GiST and GIN trgm indexes
        logger.info("Verifying spatial GiST and GIN search indexes...")
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_live_events_geom ON live_events USING GIST (geom);")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_rotterdam_districts_geom ON rotterdam_districts USING GIST (geom);")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_city_amenities_geom ON city_amenities USING GIST (geom);")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_addresses_geom ON rotterdam_addresses USING GIST (geom);")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_addresses_postcode_num ON rotterdam_addresses (postal_code, house_number);")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_addresses_street_trgm ON rotterdam_addresses USING GIN (street_name gin_trgm_ops);")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_addresses_district ON rotterdam_addresses (district);")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_addresses_purpose ON rotterdam_addresses (purpose);")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_retail_geom ON rotterdam_retail USING GIST (geom);")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_retail_name_trgm ON rotterdam_retail USING GIN (name gin_trgm_ops);")
        )

    logger.info("Database schema initialized successfully.")

    # 4. Seed initial spatial baselines
    logger.info("Seeding baseline Rotterdam districts...")
    ingestor = SpatialBaselineIngestor()
    try:
        res = await ingestor.ingest()
        logger.info("Spatial baseline seed complete: {}", res)
    finally:
        await ingestor.close()


if __name__ == "__main__":
    asyncio.run(init_database())
