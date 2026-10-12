# Rotterdam Live - Unified Backend Data Engine (rotterdamlive.nl)

High-performance, asynchronous real-time urban intelligence data platform for **Rotterdam Live** (`rotterdamlive.nl`), built for Hetzner VPS and consuming free Dutch open data streams.

---

## Architecture Overview

```
                      ┌─────────────────────────────────────────┐
                      │   Free Open Data Streams (Background)   │
                      │  P2000 RSS, NDW Garages, NDW Bridges,   │
                      │  Donkey Republic GBFS, OpenOV GTFS-RT,  │
                      │  Rijnmond RSS, Open-Meteo, DCMR Air Q.  │
                      └────────────────────┬────────────────────┘
                                           │ (Asynchronous Polling)
                                           ▼
                            ┌────────────────────────────┐
                            │      Ingestion Engine      │
                            │ (worker.py / APScheduler)  │
                            │   + PDOK Locatieserver     │
                            │   + GeoJSON Normalizer     │
                            └──────┬──────────────┬──────┘
                                   │              │
                   (Upsert Spatial)│              │(Cache Invalidation)
                                   ▼              ▼
           ┌─────────────────────────────┐  ┌─────────────────────────┐
           │   PostgreSQL 16 + PostGIS   │  │   Redis 7 (In-Memory)   │
           │  EPSG:4326 GiST Spatial Idx │  │ Quantized BBOX Caching  │
           │  ST_Within District Match   │  │ Rate Limiting & TTL     │
           │  ST_Intersects BBOX Engine  │  │ Sub-millisecond hits    │
           └──────────────┬──────────────┘  └────────────┬────────────┘
                          │                              │
                          └──────────────┬───────────────┘
                                         │
                                         ▼
                     ┌───────────────────────────────────────┐
                     │          FastAPI Async Engine         │
                     │  - Strict RFC 7946 GeoJSON Output     │
                     │  - Sub-30ms Response Latency          │
                     │  - ETag Conditional Caching           │
                     │  - Security & GZip Compression        │
                     └───────────────────┬───────────────────┘
                                         │ (HTTP / JSON)
                                         ▼
                     ┌───────────────────────────────────────┐
                     │       Svelte Map Client Frontend      │
                     │  (MapLibre / Mapbox Vector Tiles)     │
                     └───────────────────────────────────────┘
```

---

## 1. Free Open Data Integrations (100% Free / Zero API Keys Required)

| Category | Source | Protocol / Format | Polling Interval |
| :--- | :--- | :--- | :--- |
| **Emergencies** | P2000 Alarmeringen (Rotterdam-Rijnmond / VRR) | RSS 2.0 XML | 45s |
| **Geocoding** | PDOK Locatieserver (BZK) | REST / JSON | Cached (1 week) |
| **Mobility** | NDW / RDW Garages (Koopgoot, Schouwburgplein, Meent, Erasmusbrug, etc.) | REST / Socrata JSON | 60s |
| **Mobility** | NDW Brugopeningen (Erasmusbrug, Willemsbrug, Koninginnebrug, etc.) | DATEX II XML (gz) | 120s |
| **Mobility** | Donkey Republic Rotterdam GBFS (Deelfietsen) | GBFS 2.0 JSON | 60s |
| **Mobility** | OpenOV / RET Service Alerts & Verstoringen | GTFS-RT Protobuf | 30s |
| **News** | Rijnmond Nieuws Feed | RSS 2.0 XML | 300s |
| **News** | Gemeente Rotterdam Persberichten | WordPress RSS 2.0 | 300s |
| **Environment**| Open-Meteo Rotterdam Weather | REST JSON | 600s |
| **Environment**| Luchtmeetnet DCMR (Maashaven, Pleinweg, Schiedamse Vest, Botlek, etc.) | REST JSON | 900s |
| **Spatial** | PDOK CBS Wijken & Buurten WFS (Gemeente Rotterdam) | OGC WFS 2.0 GeoJSON | 24h |

---

## 2. Canonical GeoJSON Output Specification

All endpoints returning spatial items adhere to strict RFC 7946 GeoJSON FeatureCollections:

```json
{
  "type": "Feature",
  "geometry": {
    "type": "Point",
    "coordinates": [4.4777, 51.9244]
  },
  "properties": {
    "id": "p2000-86c15fee22165c37344d035891ac19cf",
    "category": "emergency",
    "subcategory": "ambulance",
    "severity": 5,
    "timestamp": "2026-10-12T13:47:16Z",
    "expires_at": "2026-10-12T15:47:16Z",
    "district": "Delfshaven",
    "title": "Ambulance met spoed naar Spangesekade in Rotterdam",
    "details": {
      "prio": 1,
      "address_query": "3027GJ Rotterdam"
    }
  }
}
```

---

## 3. Quick Start (Docker Compose)

### Prerequisites
* Docker 24+ & Docker Compose v2

### Setup & Launch
```bash
# Clone and enter directory
cd rotterdam-live-api

# Inspect / customize environment variables if needed
cp .env.example .env

# Build and start all 4 containers in the background
docker compose up -d --build

# Verify container health
docker compose ps
```

The stack runs 4 coordinated containers:
1. `rotterdam_live_db`: PostgreSQL 16 + PostGIS 3.4 with GiST spatial indexing on persistent volume `pgdata`.
2. `rotterdam_live_redis`: Redis 7 in-memory cache on persistent volume `redisdata`.
3. `rotterdam_live_api`: FastAPI ASGI service on port `8000`.
4. `rotterdam_live_worker`: Background ingestion engine polling external feeds on configured intervals.

---

## 4. API Endpoints

Interactive Swagger UI documentation is available at `http://localhost:8000/docs`.

### Unified Multi-Layer Live Feed
* **`GET /api/v1/live`**
  * `bbox=4.40,51.90,4.55,51.95` (Optional bounding-box filter)
  * `category=emergency,mobility` (Optional comma-separated filter)
  * `district=Centrum` (Optional district filter)
  * `min_severity=3` (Optional minimum severity 1-5)
  * `limit=250` & `offset=0`

### Domain Endpoints
* **`GET /api/v1/emergencies`**: P2000 Alarmeringen for Rotterdam-Rijnmond.
* **`GET /api/v1/mobility`**: Parking garage occupancy, bridge statuses, micro-mobility, RET disruptions.
* **`GET /api/v1/news`**: Geotagged Rijnmond news and Rotterdam press releases.
* **`GET /api/v1/environment`**: Open-Meteo weather metrics and DCMR air quality stations.
* **`GET /api/v1/spatial/districts`**: Official Gemeente Rotterdam district polygon boundaries (`wijk` or `buurt`).

### Health & Observability
* **`GET /health/live`**: Liveness probe (process is running).
* **`GET /health/ready`**: Readiness probe (validates PostgreSQL and Redis connection pool).

---

## 5. Local Development & Testing

```bash
# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run test suite
pytest -v
```
