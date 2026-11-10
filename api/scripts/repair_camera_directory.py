"""Retire legacy inferred cameras and repair provenance without external requests.

Run inside the API container: python scripts/repair_camera_directory.py
The camera worker calls the same idempotent repair before source refreshes.
"""
import asyncio
import json

from sqlalchemy import text

from app.cache.redis_client import close_redis_client
from app.db.session import AsyncSessionLocal, engine
from app.ingestion.camera_harvester import retire_unsupported_camera_records, invalidate_camera_cache


async def main():
    try:
        async with AsyncSessionLocal() as session:
            retired = await retire_unsupported_camera_records(session)
            await session.commit()
            count = await session.scalar(text(
                "SELECT COUNT(*) FROM city_amenities WHERE subcategory = 'camera' AND is_active"
            ))
        await invalidate_camera_cache()
        print(json.dumps({"retired_unsupported_or_duplicate": retired, "active_mapped_locations": count}))
    finally:
        await close_redis_client()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
