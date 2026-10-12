"""Active and Planned Roadworks Ingestor for Rotterdam (VGW / diensten.rotterdam.nl)."""
from datetime import datetime, timezone
from typing import Any, Dict
from app.logging import logger
from app.ingestion.base import BaseIngestor
from app.db.session import AsyncSessionLocal
from app.services.spatial_service import upsert_live_event, find_district_for_point


class RoadworksIngestor(BaseIngestor):
    """
    Ingests official active roadworks, closures, and permits from
    Gemeente Rotterdam Verkeersmaatregelen Gemeentewerken (VGW).
    """

    ROADWORKS_URL = (
        "https://diensten.rotterdam.nl/arcgis/rest/services/SB_BI/VGW_server/MapServer/0/query"
        "?where=1%3D1&outFields=*&returnGeometry=true&f=geojson&outSR=4326&resultRecordCount=300"
    )

    def __init__(self):
        super().__init__(name="roadworks", timeout_seconds=20.0)

    async def ingest(self) -> Dict[str, int]:
        """Fetch and normalize roadworks into live_events."""
        logger.info("Polling Rotterdam roadworks from diensten.rotterdam.nl (VGW)...")
        client = await self.get_client()
        try:
            res = await client.get(self.ROADWORKS_URL)
            if res.status_code != 200:
                logger.warning("Failed to fetch roadworks from VGW: status {}", res.status_code)
                return {"roadworks": 0}
            data = res.json()
        except Exception as e:
            logger.warning("Error fetching roadworks: {}", e)
            return {"roadworks": 0}

        features = data.get("features", [])
        saved = 0
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        async with AsyncSessionLocal() as session:
            for feat in features:
                props = feat.get("properties", {})
                geom = feat.get("geometry", {})
                coords = geom.get("coordinates", [])
                if not coords or len(coords) < 2:
                    continue

                status = str(props.get("STATUS", "")).strip().upper()
                # Skip explicitly rejected applications
                if status == "GEWEIGERD":
                    continue

                start_ms = props.get("STARTDATUM")
                end_ms = props.get("EINDDATUM")

                # Filter out expired roadworks
                if end_ms and end_ms < now_ms:
                    continue

                lon, lat = float(coords[0]), float(coords[1])
                obj_id = str(props.get("ID") or f"rw-{lon}-{lat}")
                straat = props.get("STRAATNAAM") or props.get("LOCATIE_ADRES") or "Wegvak"
                wijk = str(props.get("WIJK_NAAM") or "").strip()
                tekst = props.get("WERKZAAMHEDEN_TEKST") or "Wegwerkzaamheden / verkeersmaatregel"

                start_dt = (
                    datetime.fromtimestamp(start_ms / 1000.0, timezone.utc)
                    if start_ms
                    else datetime.now(timezone.utc)
                )
                end_dt = (
                    datetime.fromtimestamp(end_ms / 1000.0, timezone.utc)
                    if end_ms
                    else None
                )

                district = await find_district_for_point(lon, lat, session) or wijk

                event_data = {
                    "id": f"roadwork-{obj_id}",
                    "category": "mobility",
                    "subcategory": "roadworks",
                    "severity": 3 if "afsluiting" in tekst.lower() or "stremming" in tekst.lower() else 2,
                    "timestamp": start_dt,
                    "expires_at": end_dt,
                    "district": district,
                    "title": f"Werkzaamheden {straat}: {tekst[:80]}",
                    "details": {
                        "id": obj_id,
                        "street": straat,
                        "location_address": props.get("LOCATIE_ADRES"),
                        "district": district,
                        "work_description": tekst,
                        "status": status or "VERLEEND",
                        "start_date": start_dt.isoformat() if start_dt else None,
                        "end_date": end_dt.isoformat() if end_dt else None,
                        "area_type": props.get("GEBIEDSOORTEN_TEKST"),
                        "permit_office": props.get("WERF_NAAM"),
                    },
                    "lon": lon,
                    "lat": lat,
                }

                if await upsert_live_event(event_data, session):
                    saved += 1

        logger.info("Successfully ingested {} active Rotterdam roadworks", saved)
        return {"roadworks": saved}
