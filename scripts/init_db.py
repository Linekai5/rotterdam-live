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
        # 1. Enable PostGIS extension
        logger.info("Ensuring PostGIS extension is active...")
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))

        # 2. Create tables
        logger.info("Creating database tables if not exist...")
        await conn.run_sync(Base.metadata.create_all)

        # 3. Ensure spatial GiST indexes
        logger.info("Verifying spatial GiST indexes...")
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_live_events_geom ON live_events USING GIST (geom);")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_rotterdam_districts_geom ON rotterdam_districts USING GIST (geom);")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_city_amenities_geom ON city_amenities USING GIST (geom);")
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
