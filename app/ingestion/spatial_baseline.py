"""Ingestion of official Gemeente Rotterdam Wijk- en Buurtgrenzen (Spatial Baselines)."""
import json
from datetime import datetime, timezone
from typing import Any, Dict, List
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.ingestion.base import BaseIngestor
from app.logging import logger
from app.db.session import AsyncSessionLocal

# Seed baseline Rotterdam districts in case of offline cold start
FALLBACK_DISTRICTS = [
    {
        "code": "WK059901",
        "name": "Rotterdam Centrum",
        "district_type": "wijk",
        "coordinates": [
            [
                [4.460, 51.915],
                [4.495, 51.915],
                [4.495, 51.930],
                [4.460, 51.930],
                [4.460, 51.915],
            ]
        ],
    },
    {
        "code": "WK059903",
        "name": "Delfshaven",
        "district_type": "wijk",
        "coordinates": [
            [
                [4.425, 51.905],
                [4.460, 51.905],
                [4.460, 51.925],
                [4.425, 51.925],
                [4.425, 51.905],
            ]
        ],
    },
    {
        "code": "WK059908",
        "name": "Kralingen-Crooswijk",
        "district_type": "wijk",
        "coordinates": [
            [
                [4.495, 51.915],
                [4.535, 51.915],
                [4.535, 51.935],
                [4.495, 51.935],
                [4.495, 51.915],
            ]
        ],
    },
    {
        "code": "WK059910",
        "name": "Feijenoord",
        "district_type": "wijk",
        "coordinates": [
            [
                [4.480, 51.890],
                [4.520, 51.890],
                [4.520, 51.915],
                [4.480, 51.915],
                [4.480, 51.890],
            ]
        ],
    },
    {
        "code": "WK059905",
        "name": "Noord",
        "district_type": "wijk",
        "coordinates": [
            [
                [4.455, 51.930],
                [4.495, 51.930],
                [4.495, 51.950],
                [4.455, 51.950],
                [4.455, 51.930],
            ]
        ],
    },
    {
        "code": "WK059915",
        "name": "Charlois",
        "district_type": "wijk",
        "coordinates": [
            [
                [4.430, 51.875],
                [4.480, 51.875],
                [4.480, 51.900],
                [4.430, 51.900],
                [4.430, 51.875],
            ]
        ],
    },
]


class SpatialBaselineIngestor(BaseIngestor):
    def __init__(self):
        super().__init__(name="spatial_baseline", timeout_seconds=40.0)

    async def ingest(self) -> Dict[str, Any]:
        """Fetch and store official Rotterdam districts from PDOK WFS."""
        url = (
            "https://service.pdok.nl/cbs/wijkenbuurten/2024/wfs/v1_0?"
            "service=WFS&version=2.0.0&request=GetFeature&typeName=wijkenbuurten:wijken&"
            "outputFormat=application/json&bbox=4.3,51.8,4.7,52.05,urn:ogc:def:crs:OGC:1.3:CRS84"
        )
        
        features_to_insert = []
        try:
            client = await self.get_client()
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                for feat in data.get("features", []):
                    props = feat.get("properties", {})
                    # Gemeentecode GM0599 is Rotterdam
                    if props.get("gemeentecode") == "GM0599":
                        wijkcode = props.get("wijkcode")
                        wijknaam = props.get("wijknaam")
                        geom = feat.get("geometry", {})
                        if wijkcode and wijknaam and geom:
                            features_to_insert.append(
                                {
                                    "code": wijkcode,
                                    "name": wijknaam,
                                    "district_type": "wijk",
                                    "geometry": geom,
                                    "properties": props,
                                }
                            )
                logger.info(
                    "Fetched {} official Rotterdam districts from PDOK WFS",
                    len(features_to_insert),
                )
        except Exception as e:
            logger.warning(
                "Could not fetch PDOK WFS online ({}), using fallback baselines", e
            )

        if not features_to_insert:
            logger.info("Seeding {} baseline Rotterdam districts", len(FALLBACK_DISTRICTS))
            for fb in FALLBACK_DISTRICTS:
                features_to_insert.append(
                    {
                        "code": fb["code"],
                        "name": fb["name"],
                        "district_type": fb["district_type"],
                        "geometry": {
                            "type": "MultiPolygon",
                            "coordinates": [fb["coordinates"]],
                        },
                        "properties": {"name": fb["name"]},
                    }
                )

        # Store in database
        saved_count = 0
        async with AsyncSessionLocal() as session:
            for item in features_to_insert:
                geom_geojson_str = json.dumps(item["geometry"])
                stmt = text(
                    """
                    INSERT INTO rotterdam_districts (id, code, name, district_type, properties, geom, updated_at)
                    VALUES (:id, :code, :name, :district_type, :properties, ST_SetSRID(ST_Multi(ST_GeomFromGeoJSON(:geom_geojson)), 4326), NOW())
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        properties = EXCLUDED.properties,
                        geom = EXCLUDED.geom,
                        updated_at = NOW();
                    """
                )
                try:
                    await session.execute(
                        stmt,
                        {
                            "id": item["code"],
                            "code": item["code"],
                            "name": item["name"],
                            "district_type": item["district_type"],
                            "properties": json.dumps(item.get("properties", {})),
                            "geom_geojson": geom_geojson_str,
                        },
                    )
                    saved_count += 1
                except Exception as e:
                    logger.debug("Failed inserting district {}: {}", item["name"], e)
            await session.commit()

        return {"saved_districts": saved_count}
