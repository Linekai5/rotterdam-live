"""Rotterdam Events Domain Ingestor.

Ingests events from:
1. Ticketmaster Discovery API v2 (Ahoy, De Doelen, Luxor, Maassilo, Annabel, Rotown, etc.)
2. Rotterdam Stadium Fixtures (Stadion Feijenoord / De Kuip, Sparta-Stadion Het Kasteel, Van Donge & De Roo)
3. Municipal Festivals & Open Cultural Agendas (IFFR, Marathon, North Sea Jazz, Zomercarnaval, etc.)

Enforces Architectural Invariants:
- PostGIS ST_Within municipal validation rejects any entity outside Rotterdam boundaries.
- Zero synchronous external API calls during client requests (100% async ingested).
- High reliability with connection pooling and retry backoff.
"""
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from app.logging import logger
from app.config import settings
from app.ingestion.base import BaseIngestor
from app.db.session import AsyncSessionLocal
from app.services.events_service import upsert_rotterdam_event


class RotterdamEventsHarvester(BaseIngestor):
    """Asynchronous Harvester for Rotterdam Events, Fixtures & Festivals."""

    TICKETMASTER_URL = "https://app.ticketmaster.com/discovery/v2/events.json"

    # Stadium Fixtures Feeds (Maak-Agenda / Fixtur.es verified .ics feeds)
    FIXTURE_FEEDS = {
        "Feyenoord": {
            "url": "https://ics.fixtur.es/v2/Feyenoord.ics",
            "stadium": "Stadion Feijenoord (De Kuip)",
            "address": "Van Zandvlietplein 1",
            "postal_code": "3077 AA",
            "lon": 4.5231,
            "lat": 51.8939,
            "district": "Feijenoord",
            "home_pattern": r"^(Feyenoord)\s*-\s*(.+)",
        },
        "Sparta Rotterdam": {
            "url": "https://ics.fixtur.es/v2/Sparta-Rotterdam.ics",
            "stadium": "Sparta-Stadion Het Kasteel",
            "address": "Spartastraat 7-9",
            "postal_code": "3027 ER",
            "lon": 4.4336,
            "lat": 51.9194,
            "district": "Delfshaven",
            "home_pattern": r"^(Sparta(?:\s+Rotterdam)?)\s*-\s*(.+)",
        },
        "Excelsior": {
            "url": "https://ics.fixtur.es/v2/Excelsior.ics",
            "stadium": "Van Donge & De Roo Stadion (Woudestein)",
            "address": "Honingerdijk 110",
            "postal_code": "3062 NX",
            "lon": 4.5217,
            "lat": 51.9192,
            "district": "Kralingen-Crooswijk",
            "home_pattern": r"^(Excelsior)\s*-\s*(.+)",
        },
    }

    # Curated Municipal Festivals & Cultural Agendas in Rotterdam
    MUNICIPAL_FESTIVALS = [
        {
            "id": "fest_iffr",
            "title": "International Film Festival Rotterdam (IFFR)",
            "description": "Leading global independent cinema, digital arts, masterclasses and retrospective exhibitions.",
            "subcategory": "festival",
            "venue_name": "De Doelen & Schouwburgplein",
            "venue_address": "Schouwburgplein 50",
            "venue_postal_code": "3012 CL",
            "lon": 4.4714,
            "lat": 51.9219,
            "start_month": 1,
            "start_day": 28,
            "duration_days": 11,
            "ticket_url": "https://iffr.com",
            "image_url": "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba",
            "price_min": 12.0,
            "price_max": 180.0,
            "details": {
                "curator": "IFFR Foundation",
                "annual_visitors": 280000,
                "focus": "Independent Film & Digital Media",
            },
        },
        {
            "id": "fest_marathon",
            "title": "NN Marathon Rotterdam",
            "description": "World-renowned athletics event: the fastest 42.195 km road race in the Netherlands through the city center.",
            "subcategory": "sports",
            "venue_name": "Coolsingel / Stadhuis",
            "venue_address": "Coolsingel 40",
            "venue_postal_code": "3011 AD",
            "lon": 4.4795,
            "lat": 51.9228,
            "start_month": 4,
            "start_day": 12,
            "duration_days": 2,
            "ticket_url": "https://www.nnmarathonrotterdam.nl",
            "image_url": "https://images.unsplash.com/photo-1530549387789-4c1017266635",
            "price_min": 0.0,
            "price_max": 95.0,
            "details": {
                "curator": "Golazo Sports",
                "distance_km": 42.195,
                "participants": 50000,
                "focus": "Athletics & Urban Marathon",
            },
        },
        {
            "id": "fest_north_sea_jazz",
            "title": "NN North Sea Jazz Festival",
            "description": "The world's premier indoor jazz, soul, funk and blues music gathering across 15 stages.",
            "subcategory": "festival",
            "venue_name": "Rotterdam Ahoy",
            "venue_address": "Ahoyweg 10",
            "venue_postal_code": "3084 HN",
            "lon": 4.4882,
            "lat": 51.8831,
            "start_month": 7,
            "start_day": 10,
            "duration_days": 3,
            "ticket_url": "https://www.northseajazz.com",
            "image_url": "https://images.unsplash.com/photo-1511192336575-5a79af67a629",
            "price_min": 115.0,
            "price_max": 330.0,
            "details": {
                "curator": "Mojo Concerts",
                "stages": 15,
                "annual_visitors": 75000,
                "focus": "Jazz, Soul, R&B, Funk",
            },
        },
        {
            "id": "fest_zomercarnaval",
            "title": "Rotterdam Unlimited Zomercarnaval",
            "description": "UNESCO-recognized Caribbean street parade, Battle of Drums, and multicultural celebrations across Coolsingel.",
            "subcategory": "festival",
            "venue_name": "Coolsingel & Hofplein",
            "venue_address": "Coolsingel",
            "venue_postal_code": "3011 AA",
            "lon": 4.4790,
            "lat": 51.9215,
            "start_month": 7,
            "start_day": 25,
            "duration_days": 2,
            "ticket_url": "https://rotterdamunlimited.com",
            "image_url": "https://images.unsplash.com/photo-1514525253161-7a46d19cd819",
            "price_min": 0.0,
            "price_max": 0.0,
            "details": {
                "curator": "Rotterdam Festivals / DUCOS",
                "annual_visitors": 800000,
                "unesco_heritage": True,
                "focus": "Street Parade, Dance & World Music",
            },
        },
        {
            "id": "fest_wereldhavendagen",
            "title": "Wereldhavendagen (World Port Days)",
            "description": "Spectacular maritime event highlighting the Port of Rotterdam with ship excursions, demonstrations and fireworks.",
            "subcategory": "festival",
            "venue_name": "Willemskade & Nieuwe Maas",
            "venue_address": "Willemskade",
            "venue_postal_code": "3016 DL",
            "lon": 4.4815,
            "lat": 51.9090,
            "start_month": 9,
            "start_day": 4,
            "duration_days": 3,
            "ticket_url": "https://wereldhavendagen.nl",
            "image_url": "https://images.unsplash.com/photo-1509316975850-ff9c5deb0cd9",
            "price_min": 0.0,
            "price_max": 25.0,
            "details": {
                "curator": "Stichting Wereldhavendagen",
                "annual_visitors": 350000,
                "focus": "Maritime, Port Demonstrations, Nautical Shows",
            },
        },
        {
            "id": "fest_metropolis",
            "title": "Metropolis Festival",
            "description": "Rotterdam's longest-running free indie discovery festival in Zuiderpark featuring groundbreaking international acts.",
            "subcategory": "festival",
            "venue_name": "Zuiderpark",
            "venue_address": "Zuiderparkweg",
            "venue_postal_code": "3084 KH",
            "lon": 4.4920,
            "lat": 51.8790,
            "start_month": 7,
            "start_day": 5,
            "duration_days": 1,
            "ticket_url": "https://metropolisfestival.nl",
            "image_url": "https://images.unsplash.com/photo-1470225620780-dba8ba36b745",
            "price_min": 0.0,
            "price_max": 0.0,
            "details": {
                "curator": "Metropolis Foundation",
                "free_admission": True,
                "annual_visitors": 35000,
                "focus": "Indie, Rock, Punk, Hip-Hop",
            },
        },
        {
            "id": "fest_boothstock",
            "title": "Boothstock Festival",
            "description": "Leading electronic dance and house music festival set amidst the scenic Kralingse Bos.",
            "subcategory": "festival",
            "venue_name": "Kralingse Bos",
            "venue_address": "Langepad",
            "venue_postal_code": "3062 CJ",
            "lon": 4.5120,
            "lat": 51.9360,
            "start_month": 6,
            "start_day": 13,
            "duration_days": 1,
            "ticket_url": "https://boothstock.nl",
            "image_url": "https://images.unsplash.com/photo-1492684223066-81342ee5ff30",
            "price_min": 59.50,
            "price_max": 89.50,
            "details": {
                "curator": "Boothstock Events",
                "annual_visitors": 25000,
                "focus": "House, Techno, Electronic",
            },
        },
        {
            "id": "fest_rotterdam_pride",
            "title": "Rotterdam Pride",
            "description": "Annual celebration of diversity, human rights, and queer culture across central Rotterdam.",
            "subcategory": "cultural",
            "venue_name": "Schouwburgplein & Willemsplein",
            "venue_address": "Schouwburgplein",
            "venue_postal_code": "3012 CL",
            "lon": 4.4720,
            "lat": 51.9215,
            "start_month": 9,
            "start_day": 18,
            "duration_days": 3,
            "ticket_url": "https://rotterdam-pride.com",
            "image_url": "https://images.unsplash.com/photo-1518709268805-4e9042af9f23",
            "price_min": 0.0,
            "price_max": 0.0,
            "details": {
                "curator": "Rotterdam Pride Foundation",
                "focus": "LGBTIQ+ Culture, Pride Walk, Debate",
            },
        },
        {
            "id": "fest_momo",
            "title": "Motel Mozaïque (MOMO Festival)",
            "description": "Cutting-edge urban festival connecting music, performance art, and unconventional city guided tours.",
            "subcategory": "festival",
            "venue_name": "Theater Rotterdam & Witte de With",
            "venue_address": "Schouwburgplein 25",
            "venue_postal_code": "3012 CL",
            "lon": 4.4730,
            "lat": 51.9210,
            "start_month": 4,
            "start_day": 17,
            "duration_days": 3,
            "ticket_url": "https://motelmozaique.nl",
            "image_url": "https://images.unsplash.com/photo-1501386761578-eac5c94b800a",
            "price_min": 45.0,
            "price_max": 95.0,
            "details": {
                "curator": "Stichting Motel Mozaïque",
                "focus": "Alternative Music, Modern Dance, City Expeditions",
            },
        },
        {
            "id": "fest_blijdorp",
            "title": "Blijdorp Festival",
            "description": "Summer festival of electronic beats, hip hop, live art and open-air gastronomy at Roel Langerakpark.",
            "subcategory": "festival",
            "venue_name": "Roel Langerakpark",
            "venue_address": "Roel Langerakweg",
            "venue_postal_code": "3041 JA",
            "lon": 4.4480,
            "lat": 51.9280,
            "start_month": 8,
            "start_day": 8,
            "duration_days": 1,
            "ticket_url": "https://blijdorpfestival.nl",
            "image_url": "https://images.unsplash.com/photo-1464375117522-1311d6a5b81f",
            "price_min": 52.50,
            "price_max": 75.0,
            "details": {
                "curator": "Blijdorp Events",
                "annual_visitors": 20000,
                "focus": "Electronic, Hip-Hop, Live Art",
            },
        },
        {
            "id": "fest_baroeg_open_air",
            "title": "Baroeg Open Air",
            "description": "Alternative music festival dedicated to hard rock, metal, punk, gothic and industrial in Zuiderpark.",
            "subcategory": "festival",
            "venue_name": "Zuiderpark",
            "venue_address": "Zuiderparkweg",
            "venue_postal_code": "3084 KH",
            "lon": 4.4950,
            "lat": 51.8780,
            "start_month": 9,
            "start_day": 12,
            "duration_days": 1,
            "ticket_url": "https://baroegopenair.nl",
            "image_url": "https://images.unsplash.com/photo-1516450360452-9312f5e86fc7",
            "price_min": 17.50,
            "price_max": 25.0,
            "details": {
                "curator": "Poppodium Baroeg",
                "annual_visitors": 10000,
                "focus": "Metal, Rock, Punk, Electronic",
            },
        },
        {
            "id": "fest_museumnacht",
            "title": "Museumnacht 010",
            "description": "Nocturnal cultural journey: over 40 Rotterdam museums, art centres, and galleries open late with special shows.",
            "subcategory": "cultural",
            "venue_name": "Museumkwartier Rotterdam",
            "venue_address": "Museumpark 18",
            "venue_postal_code": "3015 CX",
            "lon": 4.4735,
            "lat": 51.9140,
            "start_month": 3,
            "start_day": 7,
            "duration_days": 1,
            "ticket_url": "https://museumnacht010.nl",
            "image_url": "https://images.unsplash.com/photo-1544620347-c4fd4a3d5957",
            "price_min": 17.50,
            "price_max": 25.0,
            "details": {
                "curator": "Museumnacht010",
                "participating_venues": 40,
                "focus": "Art, Architecture, Nocturnal Performances",
            },
        },
        {
            "id": "fest_art_week",
            "title": "Rotterdam Art Week",
            "description": "City-wide celebration of contemporary art, design fairs, and open studios centred around Van Nelle Fabriek.",
            "subcategory": "exhibition",
            "venue_name": "Van Nelle Fabriek & Museumpark",
            "venue_address": "Van Nelleweg 1",
            "venue_postal_code": "3044 BC",
            "lon": 4.4315,
            "lat": 51.9220,
            "start_month": 2,
            "start_day": 12,
            "duration_days": 4,
            "ticket_url": "https://rotterdamartweek.com",
            "image_url": "https://images.unsplash.com/photo-1579783900882-c0d3dad7b119",
            "price_min": 20.0,
            "price_max": 45.0,
            "details": {
                "curator": "Art Rotterdam",
                "focus": "Contemporary Art, Design, Architecture",
            },
        },
        {
            "id": "fest_chio",
            "title": "CHIO Rotterdam",
            "description": "The Netherlands' premier outdoor international equestrian championship in jumping and dressage at Kralingse Bos.",
            "subcategory": "sports",
            "venue_name": "Kralingse Bos",
            "venue_address": "Kralingseweg 120",
            "venue_postal_code": "3062 CG",
            "lon": 4.5150,
            "lat": 51.9330,
            "start_month": 6,
            "start_day": 18,
            "duration_days": 4,
            "ticket_url": "https://chio.nl",
            "image_url": "https://images.unsplash.com/photo-1534447677768-be436bb09401",
            "price_min": 25.0,
            "price_max": 85.0,
            "details": {
                "curator": "CHIO Foundation",
                "annual_visitors": 50000,
                "focus": "Equestrian Jumping & Dressage",
            },
        },
        {
            "id": "fest_crave",
            "title": "The Crave Festival",
            "description": "High-octane electronic and techno celebration held under the trees of Zuiderpark.",
            "subcategory": "festival",
            "venue_name": "Zuiderpark",
            "venue_address": "Zuiderparkweg",
            "venue_postal_code": "3084 KH",
            "lon": 4.4930,
            "lat": 51.8795,
            "start_month": 6,
            "start_day": 6,
            "duration_days": 1,
            "ticket_url": "https://thecrave.nl",
            "image_url": "https://images.unsplash.com/photo-1470225620780-dba8ba36b745",
            "price_min": 54.50,
            "price_max": 79.50,
            "details": {
                "curator": "The Crave Events",
                "focus": "Techno, Electro, Bass",
            },
        },
        {
            "id": "fest_abn_amro_open",
            "title": "ABN AMRO Open",
            "description": "Prestigious ATP 500 World Tennis Tournament gathering top international players at Rotterdam Ahoy.",
            "subcategory": "sports",
            "venue_name": "Rotterdam Ahoy",
            "venue_address": "Ahoyweg 10",
            "venue_postal_code": "3084 HN",
            "lon": 4.4882,
            "lat": 51.8831,
            "start_month": 2,
            "start_day": 8,
            "duration_days": 8,
            "ticket_url": "https://abnamro-open.nl",
            "image_url": "https://images.unsplash.com/photo-1595435934249-5df7ed86e1c0",
            "price_min": 35.0,
            "price_max": 140.0,
            "details": {
                "curator": "Rotterdam Ahoy / ABN AMRO",
                "tournament_level": "ATP 500",
                "annual_visitors": 120000,
                "focus": "Professional World Tennis",
            },
        },
        {
            "id": "fest_dag_romantische_muziek",
            "title": "Dag van de Romantische Muziek",
            "description": "Free romantic and classical music festival in Het Park near the Euromast with historical costumes and gazebos.",
            "subcategory": "cultural",
            "venue_name": "Het Park bij de Euromast",
            "venue_address": "Baden Powelllaan 2",
            "venue_postal_code": "3016 GJ",
            "lon": 4.4680,
            "lat": 51.9050,
            "start_month": 8,
            "start_day": 23,
            "duration_days": 1,
            "ticket_url": "https://dagvanderomantischemuziek.nl",
            "image_url": "https://images.unsplash.com/photo-1507838153414-b4b713384a76",
            "price_min": 0.0,
            "price_max": 0.0,
            "details": {
                "curator": "Stichting Dag van de Romantische Muziek",
                "free_admission": True,
                "focus": "Classical Romance, Opera, Park Concerts",
            },
        },
        {
            "id": "fest_nacht_van_de_kaap",
            "title": "Nacht van de Kaap",
            "description": "Maritime festival on Katendrecht with sea shanties, theatrical storytelling and raw port folklore.",
            "subcategory": "festival",
            "venue_name": "Katendrecht & Deliplein",
            "venue_address": "Deliplein",
            "venue_postal_code": "3072 AN",
            "lon": 4.4820,
            "lat": 51.9010,
            "start_month": 9,
            "start_day": 5,
            "duration_days": 1,
            "ticket_url": "https://denachtvandekaap.nl",
            "image_url": "https://images.unsplash.com/photo-1514525253161-7a46d19cd819",
            "price_min": 25.0,
            "price_max": 35.0,
            "details": {
                "curator": "JMR Event Makers",
                "focus": "Maritime Folklore, Cabaret, Chansons",
            },
        },
    ]

    def __init__(self):
        super().__init__(name="rotterdam_events", timeout_seconds=25.0)

    @staticmethod
    def _classify_ticketmaster(classifications: List[Dict[str, Any]]) -> str:
        """Map Ticketmaster segments and genres to canonical subcategories."""
        if not classifications:
            return "concert"
        first = classifications[0]
        segment = (first.get("segment", {}).get("name") or "").lower()
        genre = (first.get("genre", {}).get("name") or "").lower()
        subgenre = (first.get("subGenre", {}).get("name") or "").lower()

        combined = f"{segment} {genre} {subgenre}"
        if "comedy" in combined or "standup" in combined:
            return "comedy"
        if "theatre" in combined or "theater" in combined or "musical" in combined or "ballet" in combined or "dance" in combined:
            return "theatre"
        if "sports" in combined or "soccer" in combined or "football" in combined or "tennis" in combined:
            return "sports"
        if "festival" in combined:
            return "festival"
        if "film" in combined or "movie" in combined:
            return "cultural"
        if "music" in combined or "rock" in combined or "pop" in combined or "hip-hop" in combined or "electronic" in combined or "country" in combined:
            return "concert"
        return "cultural"

    async def harvest_ticketmaster(self) -> int:
        """Ingest live Rotterdam events via Ticketmaster Discovery API v2."""
        api_key = settings.TICKETMASTER_CONSUMER_KEY
        if not api_key:
            logger.warning("Ticketmaster Consumer Key missing; skipping Ticketmaster ingestion.")
            return 0

        client = await self.get_client()
        saved = 0
        current_page = 0
        total_pages = 1

        async with AsyncSessionLocal() as session:
            while current_page < min(total_pages, 5):  # Max 500 events
                params = {
                    "apikey": api_key,
                    "city": "Rotterdam",
                    "size": "100",
                    "page": str(current_page),
                    "sort": "date,asc",
                }
                try:
                    res = await client.get(self.TICKETMASTER_URL, params=params)
                    if res.status_code == 429:
                        logger.warning("Ticketmaster rate limited (429); pausing.")
                        break
                    if res.status_code != 200:
                        logger.warning("Ticketmaster API returned status {}: {}", res.status_code, res.text[:200])
                        break
                    data = res.json()
                except Exception as e:
                    logger.error("Failed to query Ticketmaster API: {}", e)
                    break

                page_info = data.get("page", {})
                total_pages = page_info.get("totalPages", 1)
                events_list = data.get("_embedded", {}).get("events", [])
                if not events_list:
                    break

                for ev in events_list:
                    ev_id = f"tm_{ev.get('id')}"
                    title = ev.get("name", "").strip()
                    if not title:
                        continue

                    venues = ev.get("_embedded", {}).get("venues", [])
                    if not venues:
                        continue
                    v = venues[0]
                    loc = v.get("location", {})
                    lon_str = loc.get("longitude")
                    lat_str = loc.get("latitude")
                    if not lon_str or not lat_str:
                        continue

                    try:
                        lon = float(lon_str)
                        lat = float(lat_str)
                    except ValueError:
                        continue

                    # Dates parsing
                    start_data = ev.get("dates", {}).get("start", {})
                    dt_str = start_data.get("dateTime")
                    if dt_str:
                        try:
                            start_dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                        except Exception:
                            start_dt = datetime.now(timezone.utc)
                    else:
                        local_date = start_data.get("localDate", "")
                        local_time = start_data.get("localTime", "20:00:00")
                        try:
                            start_dt = datetime.fromisoformat(f"{local_date}T{local_time}+01:00").astimezone(timezone.utc)
                        except Exception:
                            start_dt = datetime.now(timezone.utc)

                    end_data = ev.get("dates", {}).get("end", {})
                    end_dt = None
                    if end_data.get("dateTime"):
                        try:
                            end_dt = datetime.fromisoformat(end_data["dateTime"].replace("Z", "+00:00"))
                        except Exception:
                            pass
                    if not end_dt:
                        end_dt = start_dt + timedelta(hours=3)

                    # Classifications
                    classifications = ev.get("classifications", [])
                    subcat = self._classify_ticketmaster(classifications)

                    # Price
                    price_ranges = ev.get("priceRanges", [])
                    p_min, p_max, p_curr = None, None, "EUR"
                    if price_ranges:
                        p_min = price_ranges[0].get("min")
                        p_max = price_ranges[0].get("max")
                        p_curr = price_ranges[0].get("currency", "EUR")

                    # Hero image
                    images = ev.get("images", [])
                    img_url = images[0].get("url") if images else None
                    for img in images:
                        if img.get("ratio") == "16_9" and img.get("width", 0) >= 640:
                            img_url = img.get("url")
                            break

                    venue_name = v.get("name", "Rotterdam Venue")
                    venue_addr = v.get("address", {}).get("line1")
                    venue_postal = v.get("postalCode")

                    event_payload = {
                        "id": ev_id,
                        "title": title,
                        "description": ev.get("info") or ev.get("pleaseNote"),
                        "category": "event",
                        "subcategory": subcat,
                        "source": "ticketmaster",
                        "venue_name": venue_name,
                        "venue_address": venue_addr,
                        "venue_postal_code": venue_postal,
                        "start_time": start_dt,
                        "end_time": end_dt,
                        "lon": lon,
                        "lat": lat,
                        "price_min": p_min,
                        "price_max": p_max,
                        "price_currency": p_curr,
                        "ticket_url": ev.get("url"),
                        "image_url": img_url,
                        "status": ev.get("dates", {}).get("status", {}).get("code", "scheduled"),
                        "details": {
                            "ticketmaster_id": ev.get("id"),
                            "classifications": classifications,
                            "promoter": ev.get("promoter", {}).get("name"),
                            "age_restrictions": ev.get("ageRestrictions"),
                        },
                    }

                    ok = await upsert_rotterdam_event(event_payload, session)
                    if ok:
                        saved += 1

                current_page += 1

        logger.info("Ticketmaster ingestion cycle saved {} verified events", saved)
        return saved

    async def harvest_stadium_fixtures(self) -> int:
        """Ingest Rotterdam football club fixtures (Feyenoord, Sparta, Excelsior)."""
        client = await self.get_client()
        saved = 0
        now_utc = datetime.now(timezone.utc)
        season_cutoff = now_utc - timedelta(days=90)  # Include recent and upcoming matches

        async with AsyncSessionLocal() as session:
            for club, cfg in self.FIXTURE_FEEDS.items():
                try:
                    res = await client.get(cfg["url"])
                    if res.status_code != 200:
                        logger.warning("Failed to fetch fixtures for {}: status {}", club, res.status_code)
                        continue
                    content = res.text
                except Exception as e:
                    logger.warning("Error fetching fixtures for {}: {}", club, e)
                    continue

                events = content.split("BEGIN:VEVENT")
                for ev in events[1:]:
                    lines = ev.splitlines()
                    data = {}
                    for line in lines:
                        if ":" in line:
                            k, v = line.split(":", 1)
                            clean_k = k.split(";")[0].strip()
                            data[clean_k] = v.strip()

                    summary = data.get("SUMMARY", "")
                    dtstart_raw = data.get("DTSTART", "")
                    location = data.get("LOCATION", "").replace(r"\,", ",")

                    # Determine if it's a home game in Rotterdam
                    match = re.search(cfg["home_pattern"], summary, re.IGNORECASE)
                    is_home_by_name = match is not None
                    is_home_by_loc = "Rotterdam" in location or cfg["stadium"] in location

                    if not (is_home_by_name or is_home_by_loc):
                        continue

                    # Parse iCal datetime
                    try:
                        clean_dt = dtstart_raw.replace("Z", "")
                        if "T" in clean_dt:
                            start_dt = datetime.strptime(clean_dt, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
                        else:
                            start_dt = datetime.strptime(clean_dt, "%Y%m%d").replace(tzinfo=timezone.utc)
                    except Exception:
                        continue

                    # Ignore old matches before cutoff
                    if start_dt < season_cutoff:
                        continue

                    end_dt = start_dt + timedelta(hours=2)
                    ev_uid = data.get("UID", f"{club}_{dtstart_raw}").replace("@maak-agenda.nl", "")
                    fixture_id = f"fixture_{re.sub(r'[^a-zA-Z0-9_]', '_', ev_uid)}"

                    # Clean title: strip score parenthesis if present
                    clean_title = re.sub(r"\s*\(\d+-\d+\)", "", summary).strip()

                    event_payload = {
                        "id": fixture_id,
                        "title": f"{clean_title} — {cfg['stadium']}",
                        "description": f"Official fixture for {club} at {cfg['stadium']}.",
                        "category": "event",
                        "subcategory": "stadium_fixture",
                        "source": "stadium_fixtures",
                        "venue_name": cfg["stadium"],
                        "venue_address": cfg["address"],
                        "venue_postal_code": cfg["postal_code"],
                        "start_time": start_dt,
                        "end_time": end_dt,
                        "district": cfg["district"],
                        "lon": cfg["lon"],
                        "lat": cfg["lat"],
                        "price_min": 25.0,
                        "price_max": 85.0,
                        "price_currency": "EUR",
                        "ticket_url": f"https://www.{club.lower().replace(' ', '')}.nl/tickets",
                        "image_url": "https://images.unsplash.com/photo-1508098682722-e99c43a406b2",
                        "status": "scheduled",
                        "details": {
                            "home_club": club,
                            "match_raw": summary,
                            "stadium": cfg["stadium"],
                            "location_raw": location,
                        },
                    }

                    ok = await upsert_rotterdam_event(event_payload, session)
                    if ok:
                        saved += 1

        logger.info("Stadium fixtures harvest saved {} matches", saved)
        return saved

    async def harvest_municipal_festivals(self) -> int:
        """Ingest official Rotterdam municipal festivals and open cultural agendas."""
        saved = 0
        now_utc = datetime.now(timezone.utc)
        current_year = now_utc.year

        async with AsyncSessionLocal() as session:
            for fest in self.MUNICIPAL_FESTIVALS:
                m = fest["start_month"]
                d = fest["start_day"]
                # Calculate next occurrence for current or upcoming year
                event_year = current_year
                if now_utc.month > m or (now_utc.month == m and now_utc.day > d):
                    event_year = current_year + 1

                start_dt = datetime(event_year, m, d, 12, 0, 0, tzinfo=timezone.utc)
                end_dt = start_dt + timedelta(days=fest.get("duration_days", 1))

                fest_id = f"{fest['id']}_{event_year}"

                event_payload = {
                    "id": fest_id,
                    "title": f"{fest['title']} ({event_year})",
                    "description": fest.get("description"),
                    "category": "event",
                    "subcategory": fest["subcategory"],
                    "source": "municipal_festivals",
                    "venue_name": fest["venue_name"],
                    "venue_address": fest["venue_address"],
                    "venue_postal_code": fest["venue_postal_code"],
                    "start_time": start_dt,
                    "end_time": end_dt,
                    "lon": fest["lon"],
                    "lat": fest["lat"],
                    "price_min": fest.get("price_min"),
                    "price_max": fest.get("price_max"),
                    "price_currency": "EUR",
                    "ticket_url": fest.get("ticket_url"),
                    "image_url": fest.get("image_url"),
                    "status": "scheduled",
                    "details": fest.get("details", {}),
                }

                ok = await upsert_rotterdam_event(event_payload, session)
                if ok:
                    saved += 1

        logger.info("Municipal festivals harvest saved {} events", saved)
        return saved

    async def ingest(self) -> Dict[str, Any]:
        """Run complete events ingestion cycle across all data feeds."""
        logger.info("Starting complete /events domain ingestion cycle...")
        tm_saved = await self.harvest_ticketmaster()
        stadium_saved = await self.harvest_stadium_fixtures()
        festivals_saved = await self.harvest_municipal_festivals()

        total = tm_saved + stadium_saved + festivals_saved
        logger.info(
            "Events ingestion cycle finished: {} total (TM: {}, Stadium: {}, Festivals: {})",
            total,
            tm_saved,
            stadium_saved,
            festivals_saved,
        )
        return {
            "total_saved": total,
            "ticketmaster": tm_saved,
            "stadium_fixtures": stadium_saved,
            "municipal_festivals": festivals_saved,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
