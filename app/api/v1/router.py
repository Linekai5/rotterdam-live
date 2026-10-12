"""API v1 Router aggregation."""
from fastapi import APIRouter
from app.api.v1.emergencies import router as emergencies_router
from app.api.v1.mobility import router as mobility_router
from app.api.v1.news import router as news_router
from app.api.v1.environment import router as environment_router
from app.api.v1.spatial import router as spatial_router
from app.api.v1.live import router as live_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(emergencies_router)
api_v1_router.include_router(mobility_router)
api_v1_router.include_router(news_router)
api_v1_router.include_router(environment_router)
api_v1_router.include_router(spatial_router)
api_v1_router.include_router(live_router)
