"""FastAPI dependencies for query parameters and database sessions."""
from typing import Optional, Tuple
from fastapi import Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db


def parse_bbox_param(
    bbox: Optional[str] = Query(
        None,
        description="Bounding box filter in EPSG:4326 format: min_lon,min_lat,max_lon,max_lat (e.g. 4.40,51.90,4.55,51.95)",
    )
) -> Optional[Tuple[float, float, float, float]]:
    """Parse comma-separated bbox string into float tuple."""
    if not bbox:
        return None
    try:
        parts = [float(x.strip()) for x in bbox.split(",")]
        if len(parts) != 4:
            raise ValueError()
        min_lon, min_lat, max_lon, max_lat = parts
        if not (-180 <= min_lon <= 180 and -90 <= min_lat <= 90 and -180 <= max_lon <= 180 and -90 <= max_lat <= 90):
            raise ValueError()
        if min_lon > max_lon or min_lat > max_lat:
            raise ValueError()
        return (min_lon, min_lat, max_lon, max_lat)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid bbox parameter. Format must be 'min_lon,min_lat,max_lon,max_lat' within valid coordinate ranges.",
        )
