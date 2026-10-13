"""Local & PDOK Locatieserver Geocoder for Rotterdam addresses."""
import re
from typing import Dict, List, Optional, Tuple
import httpx
from app.logging import logger
from app.cache.redis_client import get_cached_json, set_cached_json
from app.config import settings

# In-memory LRU-like dictionary cache for fast hits
_MEMORY_GEO_CACHE: Dict[str, Tuple[float, float]] = {
    "rotterdam": (settings.ROTTERDAM_CENTER_LON, settings.ROTTERDAM_CENTER_LAT),
    "coolsingel": (4.4792, 51.9225),
    "hofplein": (4.4788, 51.9247),
    "weend": (4.4735, 51.9238),
    "blaak": (4.4891, 51.9197),
    "kop van zuid": (4.4894, 51.9054),
}

# Regex to capture Dutch postal codes (4 digits + 2 letters, e.g. 3027GJ or 3027 GJ)
POSTCODE_REGEX = re.compile(r"\b([1-9][0-9]{3}\s?[a-zA-Z]{2})\b")


class GeocodingService:
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=5.0,
                headers={"User-Agent": "RotterdamLive-Geocoder/1.0"},
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def geocode(self, query: str) -> Tuple[float, float]:
        """
        Geocode an address or text string in Rotterdam into (lon, lat).
        Returns (lon, lat) tuple. Defaults to Rotterdam center on failure.
        """
        clean_q = query.strip().lower()
        if not clean_q:
            return (settings.ROTTERDAM_CENTER_LON, settings.ROTTERDAM_CENTER_LAT)

        # 1. Check in-memory cache
        if clean_q in _MEMORY_GEO_CACHE:
            return _MEMORY_GEO_CACHE[clean_q]

        # 2. Check Redis cache
        cache_key = f"geo:{clean_q}"
        cached = await get_cached_json(cache_key)
        if cached and isinstance(cached, list) and len(cached) == 2:
            _MEMORY_GEO_CACHE[clean_q] = (cached[0], cached[1])
            return (cached[0], cached[1])

        # 3. Query PDOK Locatieserver (100% free open API)
        search_term = query
        if "rotterdam" not in clean_q and "rijnmond" not in clean_q:
            search_term = f"{query} Rotterdam"

        try:
            client = await self._get_client()
            url = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/free"
            params = {"q": search_term, "rows": "1", "fq": "gemeentenaam:Rotterdam"}
            
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                docs = data.get("response", {}).get("docs", [])
                if docs:
                    # Centroide_ll format: "POINT(4.4419 51.9213)"
                    centroide = docs[0].get("centroide_ll")
                    if centroide and "POINT(" in centroide:
                        coords_str = centroide.replace("POINT(", "").replace(")", "").strip()
                        parts = coords_str.split()
                        if len(parts) >= 2:
                            lon = float(parts[0])
                            lat = float(parts[1])
                            
                            # Cache result
                            _MEMORY_GEO_CACHE[clean_q] = (lon, lat)
                            await set_cached_json(cache_key, [lon, lat], ttl_seconds=86400 * 7)
                            return (lon, lat)
        except Exception as e:
            logger.debug("PDOK geocoding lookup failed for '{}': {}", query, e)

        # Fallback to Rotterdam center
        return (settings.ROTTERDAM_CENTER_LON, settings.ROTTERDAM_CENTER_LAT)


geocoder = GeocodingService()
