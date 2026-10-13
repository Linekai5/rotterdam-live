"""News & Civic Feeds Ingestor (Rijnmond & Gemeente Rotterdam Persberichten)."""
import re
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Tuple
import feedparser
from app.ingestion.base import BaseIngestor
from app.logging import logger
from app.services.spatial_service import upsert_live_event
from app.db.session import AsyncSessionLocal
from app.config import settings

RIJNMOND_NEWS_URL = "https://www.rijnmond.nl/rss/nieuws"
GEMEENTE_PERS_URL = "https://persberichtenrotterdam.nl/feed/"

# Neighborhood dictionary with approximate coordinates
ROTTERDAM_NEIGHBORHOOD_COORDS = {
    "centrum": (4.4792, 51.9225, "Rotterdam Centrum"),
    "coolsingel": (4.4792, 51.9225, "Rotterdam Centrum"),
    "hofplein": (4.4788, 51.9247, "Rotterdam Centrum"),
    "blaak": (4.4891, 51.9197, "Rotterdam Centrum"),
    "delfshaven": (4.4485, 51.9075, "Delfshaven"),
    "kralingen": (4.5098, 51.9272, "Kralingen-Crooswijk"),
    "crooswijk": (4.4925, 51.9333, "Kralingen-Crooswijk"),
    "feijenoord": (4.5000, 51.9050, "Feijenoord"),
    "feyenoord": (4.5000, 51.9050, "Feijenoord"),
    "kuip": (4.5233, 51.8939, "Feijenoord"),
    "kop van zuid": (4.4894, 51.9054, "Feijenoord"),
    "noord": (4.4750, 51.9400, "Noord"),
    "blijdorp": (4.4550, 51.9320, "Noord"),
    "overschie": (4.4300, 51.9450, "Overschie"),
    "charlois": (4.4550, 51.8880, "Charlois"),
    "ijsselmonde": (4.5450, 51.8950, "IJsselmonde"),
    "prins alexander": (4.5550, 51.9500, "Prins Alexander"),
    "hoogvliet": (4.3550, 51.8670, "Hoogvliet"),
    "haven": (4.3000, 51.9000, "Waalhaven-Eemhaven"),
}


def detect_rotterdam_neighborhood(text: str) -> Tuple[float, float, Optional[str]]:
    """Scan news text for mentioned Rotterdam neighborhoods."""
    lower = text.lower()
    for keyword, (lon, lat, district) in ROTTERDAM_NEIGHBORHOOD_COORDS.items():
        if re.search(rf"\b{re.escape(keyword)}\b", lower):
            return (lon, lat, district)
    return (settings.ROTTERDAM_CENTER_LON, settings.ROTTERDAM_CENTER_LAT, "Rotterdam")


class NewsIngestor(BaseIngestor):
    def __init__(self):
        super().__init__(name="news_civic", timeout_seconds=20.0)

    async def ingest(self) -> Dict[str, Any]:
        """Ingest Rijnmond RSS and Gemeente Rotterdam Persberichten."""
        rijnmond_count = await self._ingest_feed(
            url=RIJNMOND_NEWS_URL,
            source_name="Rijnmond",
            subcategory="regional_news",
        )
        pers_count = await self._ingest_feed(
            url=GEMEENTE_PERS_URL,
            source_name="Gemeente Rotterdam",
            subcategory="city_press",
        )
        return {"rijnmond_news": rijnmond_count, "gemeente_press": pers_count}

    async def _ingest_feed(
        self, url: str, source_name: str, subcategory: str
    ) -> int:
        client = await self.get_client()
        saved = 0
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning("Feed {} returned status {}", url, resp.status_code)
                return 0

            feed = feedparser.parse(resp.text)
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(days=2)

            async with AsyncSessionLocal() as session:
                for entry in feed.entries[:25]:
                    title = entry.get("title", "").strip()
                    summary = entry.get("summary", entry.get("description", "")).strip()
                    link = entry.get("link", "")
                    guid = entry.get("id", entry.get("guid", link))
                    if not guid:
                        guid = hashlib.md5((title + link).encode()).hexdigest()

                    # Strip HTML tags from summary
                    clean_summary = re.sub(r"<[^>]+>", "", summary).strip()

                    # Publication date
                    published_parsed = entry.get("published_parsed")
                    if published_parsed:
                        ts = datetime(*published_parsed[:6], tzinfo=timezone.utc)
                    else:
                        ts = now

                    # Tag location & district
                    combined_text = f"{title} {clean_summary}"
                    lon, lat, district = detect_rotterdam_neighborhood(combined_text)

                    # Determine severity
                    is_breaking = "breaking" in [
                        t.get("term", "").lower() for t in entry.get("tags", [])
                    ] or "groot ongeval" in combined_text.lower()
                    severity = 3 if is_breaking else 1

                    event_id = f"news-{hashlib.md5(guid.encode()).hexdigest()[:16]}"

                    event_data = {
                        "id": event_id,
                        "category": "news",
                        "subcategory": subcategory,
                        "severity": severity,
                        "timestamp": ts,
                        "expires_at": expires_at,
                        "district": district,
                        "title": title,
                        "details": {
                            "source": source_name,
                            "summary": clean_summary[:500],
                            "link": link,
                            "is_breaking": is_breaking,
                        },
                        "lon": lon,
                        "lat": lat,
                    }
                    if await upsert_live_event(event_data, session):
                        saved += 1
        except Exception as e:
            logger.warning("Error ingesting feed {} ({}): {}", source_name, url, e)
        return saved
