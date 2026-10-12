"""Ingestion task scheduler and orchestration engine."""
import asyncio
from datetime import datetime, timezone
from sqlalchemy import text
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.logging import logger
from app.config import settings
from app.db.session import AsyncSessionLocal
from app.cache.redis_client import delete_cache_pattern

from app.ingestion.spatial_baseline import SpatialBaselineIngestor
from app.ingestion.p2000 import P2000Ingestor
from app.ingestion.mobility import MobilityIngestor
from app.ingestion.news import NewsIngestor
from app.ingestion.environment import EnvironmentIngestor
from app.ingestion.amenities import MunicipalAmenitiesIngestor
from app.ingestion.roadworks import RoadworksIngestor
from app.ingestion.utilities import WaterwaysIngestor, PowerOutageIngestor
from app.ingestion.camera_harvester import RotterdamCameraHarvester
from app.ingestion.bag_harvester import RotterdamBAGHarvester
from app.ingestion.retail_harvester import RotterdamRetailHarvester


class IngestionScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.spatial_ingestor = SpatialBaselineIngestor()
        self.p2000_ingestor = P2000Ingestor()
        self.mobility_ingestor = MobilityIngestor()
        self.news_ingestor = NewsIngestor()
        self.environment_ingestor = EnvironmentIngestor()
        self.amenities_ingestor = MunicipalAmenitiesIngestor()
        self.roadworks_ingestor = RoadworksIngestor()
        self.waterways_ingestor = WaterwaysIngestor()
        self.power_outage_ingestor = PowerOutageIngestor()
        self.camera_harvester = RotterdamCameraHarvester()
        self.bag_harvester = RotterdamBAGHarvester()
        self.retail_harvester = RotterdamRetailHarvester()
        self._is_running = False

    async def _safe_run(self, name: str, coro_func):
        """Run ingestion task with error trapping so one failed task never halts others."""
        try:
            await coro_func()
            # Invalidate cached route queries
            await delete_cache_pattern(f"events:{name}*")
            await delete_cache_pattern("events:all*")
        except Exception as e:
            logger.error("Error running scheduled job '{}': {}", name, e)

    async def cleanup_expired_events(self):
        """Purge stale events older than 3 days from database."""
        try:
            async with AsyncSessionLocal() as session:
                stmt = text(
                    """
                    DELETE FROM live_events
                    WHERE expires_at IS NOT NULL 
                      AND expires_at < NOW() - INTERVAL '3 days';
                    """
                )
                res = await session.execute(stmt)
                await session.commit()
                if res.rowcount > 0:
                    logger.info("Cleaned up {} expired events from live_events", res.rowcount)
        except Exception as e:
            logger.debug("Expired events cleanup failed: {}", e)

    def start(self):
        """Register all jobs and start the scheduler."""
        if self._is_running:
            return

        logger.info("Configuring Ingestion Scheduler intervals...")

        # 1. P2000 Emergencies
        self.scheduler.add_job(
            self._safe_run,
            "interval",
            seconds=settings.P2000_POLL_INTERVAL_SECONDS,
            args=["emergency", self.p2000_ingestor.ingest],
            id="job_p2000",
            replace_existing=True,
        )

        # 2. Mobility (Garages, Bridges, GBFS, Transit alerts)
        self.scheduler.add_job(
            self._safe_run,
            "interval",
            seconds=settings.MOBILITY_POLL_INTERVAL_SECONDS,
            args=["mobility", self.mobility_ingestor.ingest],
            id="job_mobility",
            replace_existing=True,
        )

        # 3. News (Rijnmond & Persberichten)
        self.scheduler.add_job(
            self._safe_run,
            "interval",
            seconds=settings.NEWS_POLL_INTERVAL_SECONDS,
            args=["news", self.news_ingestor.ingest],
            id="job_news",
            replace_existing=True,
        )

        # 4. Environment (Open-Meteo & DCMR Air Quality)
        self.scheduler.add_job(
            self._safe_run,
            "interval",
            seconds=settings.WEATHER_POLL_INTERVAL_SECONDS,
            args=["environment", self.environment_ingestor.ingest],
            id="job_environment",
            replace_existing=True,
        )

        # 5. Spatial Baselines (daily)
        self.scheduler.add_job(
            self._safe_run,
            "interval",
            hours=settings.SPATIAL_BASELINE_SYNC_HOURS,
            args=["spatial", self.spatial_ingestor.ingest],
            id="job_spatial_baseline",
            replace_existing=True,
        )

        # 6. Roadworks & Closures (15 min)
        self.scheduler.add_job(
            self._safe_run,
            "interval",
            seconds=settings.ROADWORKS_POLL_INTERVAL_SECONDS,
            args=["mobility", self.roadworks_ingestor.ingest],
            id="job_roadworks",
            replace_existing=True,
        )

        # 7. Maritime Waterways (10 min)
        self.scheduler.add_job(
            self._safe_run,
            "interval",
            seconds=settings.WATERWAYS_POLL_INTERVAL_SECONDS,
            args=["environment", self.waterways_ingestor.ingest],
            id="job_waterways",
            replace_existing=True,
        )

        # 8. Electricity Grid & Power Outages (15 min)
        self.scheduler.add_job(
            self._safe_run,
            "interval",
            seconds=settings.POWER_OUTAGE_POLL_INTERVAL_SECONDS,
            args=["utility", self.power_outage_ingestor.ingest],
            id="job_power_outages",
            replace_existing=True,
        )

        # 9. Municipal Civic Amenities (toilets, water taps, EV chargers, aeds - daily)
        self.scheduler.add_job(
            self._safe_run,
            "interval",
            hours=settings.AMENITIES_SYNC_HOURS,
            args=["amenity", self.amenities_ingestor.ingest],
            id="job_amenities",
            replace_existing=True,
        )

        # 10. Dedicated Rotterdam Outdoor Camera Harvester (every 6 hours)
        self.scheduler.add_job(
            self._safe_run,
            "interval",
            hours=6,
            args=["cameras", self.camera_harvester.ingest],
            id="job_camera_harvester",
            replace_existing=True,
        )

        # 11. Rotterdam Retail Infrastructure Harvester (daily)
        self.scheduler.add_job(
            self._safe_run,
            "interval",
            hours=24,
            args=["retail", self.retail_harvester.ingest],
            id="job_retail_harvester",
            replace_existing=True,
        )

        # 12. Kadaster BAG Address Harvester (weekly)
        self.scheduler.add_job(
            self._safe_run,
            "interval",
            days=7,
            args=["bag_addresses", self.bag_harvester.ingest],
            id="job_bag_harvester",
            replace_existing=True,
        )

        # 13. Database Cleanup
        self.scheduler.add_job(
            self.cleanup_expired_events,
            "interval",
            minutes=15,
            id="job_cleanup_expired",
            replace_existing=True,
        )

        self.scheduler.start()
        self._is_running = True
        logger.info("Ingestion Scheduler successfully started.")

    async def run_initial_seed(self):
        """Execute one complete ingestion pass on application startup."""
        logger.info("Triggering initial bootstrap ingestion pass...")
        await self._safe_run("spatial", self.spatial_ingestor.ingest)
        await self._safe_run("emergency", self.p2000_ingestor.ingest)
        await self._safe_run("mobility", self.mobility_ingestor.ingest)
        await self._safe_run("roadworks", self.roadworks_ingestor.ingest)
        await self._safe_run("news", self.news_ingestor.ingest)
        await self._safe_run("environment", self.environment_ingestor.ingest)
        await self._safe_run("waterways", self.waterways_ingestor.ingest)
        await self._safe_run("utility", self.power_outage_ingestor.ingest)
        await self._safe_run("amenity", self.amenities_ingestor.ingest)
        await self._safe_run("cameras", self.camera_harvester.ingest)
        await self._safe_run("retail", self.retail_harvester.ingest)
        logger.info("Initial bootstrap ingestion pass finished.")

    async def stop(self):
        """Shutdown scheduler cleanly."""
        if self._is_running:
            self.scheduler.shutdown(wait=False)
            self._is_running = False
            await self.spatial_ingestor.close()
            await self.p2000_ingestor.close()
            await self.mobility_ingestor.close()
            await self.roadworks_ingestor.close()
            await self.news_ingestor.close()
            await self.environment_ingestor.close()
            await self.waterways_ingestor.close()
            await self.power_outage_ingestor.close()
            await self.amenities_ingestor.close()
            await self.camera_harvester.close()
            await self.bag_harvester.close()
            await self.retail_harvester.close()
            logger.info("Ingestion Scheduler stopped cleanly.")


scheduler = IngestionScheduler()
