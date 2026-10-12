"""FastAPI Main Application for Rotterdam Live Unified Data Engine."""
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.logging import setup_logging, logger
from app.api.v1.router import api_v1_router
from app.api.v1.health import router as health_router
from app.cache.redis_client import close_redis_client
from app.services.geocoder import geocoder


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add standard security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


class PerformanceHeaderMiddleware(BaseHTTPMiddleware):
    """Measure server execution time and inject X-Process-Time-Ms header."""

    async def dispatch(self, request: Request, call_next):
        start_time = time.perf_counter()
        response = await call_next(request)
        process_time_ms = (time.perf_counter() - start_time) * 1000.0
        response.headers["X-Process-Time-Ms"] = f"{process_time_ms:.2f}"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context managing startup and shutdown."""
    setup_logging()
    logger.info("Initializing Rotterdam Live API ({})", settings.PROJECT_NAME)
    logger.info("Operating environment: {}", settings.ENVIRONMENT)

    yield

    logger.info("Shutting down Rotterdam Live API...")
    await close_redis_client()
    await geocoder.close()
    logger.info("Rotterdam Live API successfully stopped.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "Core backend data platform for Rotterdam Live (rotterdamlive.nl). "
        "Provides real-time urban intelligence for emergencies, mobility, "
        "news, environment, and geospatial baselines in canonical GeoJSON format."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# 1. Performance timing header
app.add_middleware(PerformanceHeaderMiddleware)

# 2. Security headers
app.add_middleware(SecurityHeadersMiddleware)

# 3. GZip response compression for large GeoJSON payloads (> 500 bytes)
app.add_middleware(GZipMiddleware, minimum_size=500)

# 4. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["ETag", "X-Process-Time-Ms"],
)

# Mount Routers
app.include_router(health_router)
app.include_router(api_v1_router)


@app.get("/", tags=["Root"])
async def root():
    """Root info endpoint."""
    return {
        "service": settings.PROJECT_NAME,
        "version": "1.0.0",
        "documentation": "/docs",
        "health": "/health/ready",
        "endpoints": {
            "emergencies": "/api/v1/emergencies",
            "mobility": "/api/v1/mobility",
            "news": "/api/v1/news",
            "environment": "/api/v1/environment",
            "spatial": "/api/v1/spatial/districts",
            "live_unified": "/api/v1/live",
            "amenities": "/api/v1/amenities",
            "utilities": "/api/v1/utilities/power-outages",
        },
    }
