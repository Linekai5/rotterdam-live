"""P2000 Alarmeringen Rotterdam-Rijnmond RSS Ingestor."""
import re
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Tuple
import feedparser
from app.ingestion.base import BaseIngestor
from app.logging import logger
from app.services.geocoder import geocoder, POSTCODE_REGEX
from app.services.spatial_service import find_district_for_point, upsert_live_event
from app.db.session import AsyncSessionLocal
from app.config import settings

P2000_RSS_URL = "https://alarmeringen.nl/feeds/region/rotterdam-rijnmond.rss"


def parse_p2000_service(text: str) -> str:
    """Classify emergency discipline from message text."""
    lower = text.lower()
    if "ambu" in lower or "ambulance" in lower or "dia:" in lower:
        return "ambulance"
    if any(k in lower for k in ("brand", "brandw", "brw", "kaz", "ts-", "rv-", "al-")):
        return "brandweer"
    if any(k in lower for k in ("politie", "ongeval", "dier in problemen", "letsel", "icnum")):
        return "politie"
    if "trauma" in lower or "lifeliner" in lower:
        return "traumahelikopter"
    if "kustwacht" in lower or "redding" in lower:
        return "kustwacht"
    return "hulpdienst"


def parse_p2000_severity(text: str) -> Tuple[int, int]:
    """Return (severity_1_to_5, prio_number)."""
    lower = text.lower()
    if "a1 " in lower or "prio 1" in lower or "reanimatie" in lower or "grote brand" in lower:
        return (5, 1)
    if "a2 " in lower or "prio 2" in lower or "spoed" in lower:
        return (4, 2)
    if "b1 " in lower:
        return (3, 3)
    if "b2 " in lower or "prio 3" in lower:
        return (2, 4)
    return (1, 5)


def extract_address_query(title: str, description: str) -> str:
    """Extract street and city/zip code from P2000 raw text."""
    # Check postal code first
    pc_match = POSTCODE_REGEX.search(title)
    if pc_match:
        # e.g. "3027GJ Rotterdam"
        return f"{pc_match.group(1)} Rotterdam"

    # Description often has: "Ambulance met spoed naar [Street] in [City]"
    desc_match = re.search(r"naar\s+(.*?)\s+in\s+([a-zA-Z\-]+)", description, re.IGNORECASE)
    if desc_match:
        street = desc_match.group(1).strip()
        city = desc_match.group(2).strip()
        return f"{street}, {city}"

    # Fallback to description without prefixes
    clean_desc = re.sub(
        r"^(ambulance|brandweer|politie)\s+(met spoed\s+|met gepaste spoed\s+)?(naar\s+)?",
        "",
        description,
        flags=re.IGNORECASE,
    ).strip()
    return clean_desc or title


class P2000Ingestor(BaseIngestor):
    def __init__(self):
        super().__init__(name="p2000_alarmeringen", timeout_seconds=15.0)

    async def ingest(self) -> Dict[str, Any]:
        """Scrape, parse, geocode, and store P2000 live events."""
        client = await self.get_client()
        resp = await client.get(
            P2000_RSS_URL,
            headers={"User-Agent": "curl/8.5.0", "Accept": "*/*"}
        )
        if resp.status_code != 200:
            raise RuntimeError(f"P2000 RSS responded with status {resp.status_code}")

        feed = feedparser.parse(resp.text)
        entries = feed.entries
        logger.info("Parsed {} P2000 RSS items from feed", len(entries))

        ingested_count = 0
        async with AsyncSessionLocal() as session:
            for entry in entries:
                title = entry.get("title", "")
                desc = entry.get("description", "")
                link = entry.get("link", "")
                guid = entry.get("guid", entry.get("id", ""))
                if not guid:
                    guid = hashlib.md5((title + desc).encode()).hexdigest()

                event_id = f"p2000-{guid}"

                # Parse publication time
                published_parsed = entry.get("published_parsed")
                if published_parsed:
                    ts = datetime(*published_parsed[:6], tzinfo=timezone.utc)
                else:
                    ts = datetime.now(timezone.utc)

                # Events expire 2 hours after reporting
                expires_at = ts + timedelta(hours=2)

                # Parse domain attributes
                subcategory = parse_p2000_service(title + " " + desc)
                severity, prio = parse_p2000_severity(title + " " + desc)

                # Geocode address
                addr_query = extract_address_query(title, desc)
                lon, lat = await geocoder.geocode(addr_query)

                # Determine district via PostGIS ST_Within
                district = await find_district_for_point(lon, lat, session)

                clean_title = desc if desc else title

                event_data = {
                    "id": event_id,
                    "category": "emergency",
                    "subcategory": subcategory,
                    "severity": severity,
                    "timestamp": ts,
                    "expires_at": expires_at,
                    "district": district,
                    "title": clean_title,
                    "details": {
                        "raw_title": title,
                        "raw_description": desc,
                        "prio": prio,
                        "link": link,
                        "address_query": addr_query,
                    },
                    "lon": lon,
                    "lat": lat,
                }

                if await upsert_live_event(event_data, session):
                    ingested_count += 1

        logger.info("Successfully ingested {} P2000 emergency events", ingested_count)
        return {"ingested_p2000": ingested_count}
