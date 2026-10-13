"""API v1 Router aggregation."""
from fastapi import APIRouter
from app.api.v1.emergencies import router as emergencies_router
from app.api.v1.mobility import router as mobility_router
from app.api.v1.news import router as news_router
from app.api.v1.environment import router as environment_router
from app.api.v1.spatial import router as spatial_router
from app.api.v1.live import router as live_router
from app.api.v1.amenities import router as amenities_router
from app.api.v1.utilities import router as utilities_router
from app.api.v1.addresses import router as addresses_router
from app.api.v1.retail import router as retail_router
from app.api.v1.search import router as search_router
from app.api.v1.weather import router as weather_router
from app.api.v1.living import router as living_router
from app.api.v1.events import router as events_router
from app.api.v1.crowd import router as crowd_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(emergencies_router)
api_v1_router.include_router(mobility_router)
api_v1_router.include_router(news_router)
api_v1_router.include_router(environment_router)
api_v1_router.include_router(spatial_router)
api_v1_router.include_router(live_router)
api_v1_router.include_router(amenities_router)
api_v1_router.include_router(utilities_router)
api_v1_router.include_router(addresses_router)
api_v1_router.include_router(retail_router)
api_v1_router.include_router(search_router)
api_v1_router.include_router(weather_router)
api_v1_router.include_router(living_router)
api_v1_router.include_router(events_router)
api_v1_router.include_router(crowd_router)

