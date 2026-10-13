"""Rotterdam Crowdness Engine Harvester (Platform v1.9.0).

Executes 100% of the mathematical derivations, live residual logging, and forecast projections
in the background worker daemon every 10 minutes. Zero in-request computation invariant.
"""
from typing import Any, Dict
from app.logging import logger
from app.ingestion.base import BaseIngestor
from app.db.session import AsyncSessionLocal
from app.services.crowd_engine import execute_crowdness_cycle


class RotterdamCrowdHarvester(BaseIngestor):
    """
    Background harvester for calculating the Normalized Crowdness Index across all 19
    Rotterdam municipal districts, logging to crowd_telemetry_history and compiling
    sub-5ms snapshots to Redis.
    """

    def __init__(self):
        super().__init__(name="crowd_engine", timeout_seconds=30.0)

    async def ingest(self) -> Dict[str, Any]:
        """Execute one complete crowdness evaluation cycle."""
        logger.info("Executing Rotterdam Crowdness derivation cycle...")
        async with AsyncSessionLocal() as session:
            try:
                result = await execute_crowdness_cycle(session)
                logger.info("Rotterdam Crowdness derivation cycle complete: {}", result)
                return result
            except Exception as e:
                logger.error("Error during crowdness derivation cycle: {}", e)
                raise
