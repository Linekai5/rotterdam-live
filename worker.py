"""Standalone Background Ingestion Worker Process."""
import asyncio
import signal
import sys
from app.config import settings
from app.logging import setup_logging, logger
from app.ingestion.scheduler import scheduler


async def main():
    setup_logging()
    logger.info("Starting Rotterdam Live Ingestion Worker Daemon...")
    logger.info("Ingestion targets: P2000, Garages, Bridges, GBFS, RET Transit, News, Open-Meteo, DCMR Air Quality, Living, Events, Crowdness Engine")

    # Handle graceful termination signals
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def signal_handler():
        logger.info("Shutdown signal received, terminating worker...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Signal handling on Windows or restricted platforms
            pass

    # Start scheduled periodic jobs
    scheduler.start()

    # Trigger initial bootstrap seed run
    try:
        await scheduler.run_initial_seed()
    except Exception as e:
        logger.error("Error during initial bootstrap seed: {}", e)

    logger.info("Ingestion Worker is active and polling external feeds.")

    # Keep worker alive until shutdown event
    await stop_event.wait()

    logger.info("Stopping Ingestion Worker...")
    await scheduler.stop()
    logger.info("Ingestion Worker terminated cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
