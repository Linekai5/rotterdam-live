# Map feed and camera-source audit — 10 November 2026

This audit used the local FastAPI service on port 8000, with Vite forwarding
requests from port 5173. It is a development check, not a production deployment
or an independent certification of provider accuracy.

## What was actually failing

The audit did **not** reproduce a general API outage: all twelve existing map
datasets returned HTTP 200 and populated GeoJSON, including their common category
filters. Search and the Centrum district passport also worked. A feed with no
records in a particular viewport/time/category is different from a failed request.
The frontend should show those states separately and make selected markers visible.

The camera data had a substantive source problem. The old camera harvester treated
shops, restaurants, gates, stations and viewpoints as proof that cameras existed,
and advertised guessed webcam URLs as public footage. Checking a municipal boundary
only verifies geography; it does not verify a camera or a stream. Sample URL checks
found HTTP 404s, HTML pages masquerading as JPG snapshots, a TLS hostname mismatch,
and a descriptive placeholder YouTube video ID. None established working footage.

Two narrower filter defects were also corrected:

- Camera `has_live_feed=true` and `false` conditions overlapped for contradictory
  flags/URLs. They now use a single predicate and its inverse; empty URL strings
  do not constitute footage. Camera cache versions were changed with the fix.
- Retail parsed bounding boxes without the shared coordinate/range validation.
  Reversed bounds, out-of-range coordinates and NaN could reach PostGIS rather
  than returning a consistent HTTP 400. The route now uses the shared parser
  before cache or database access.

## API results at the initial map bounds

Requests used `bbox=4.379,51.861,4.602,51.995` and `limit=150`. Counts below are
records returned, not a promise of complete city coverage. District/crowd feeds
are citywide polygon collections and intentionally return 19; the frontend
filters them to the visible area. Other 150-record results reached the requested
cap. News and dispatch counts change as worker updates arrive.

| Layer / filter | Route below `/api/v1` | HTTP | Returned |
| --- | --- | --- | ---: |
| Events, upcoming | `/events` | 200 | 150 |
| Neighbourhoods | `/spatial/districts` | 200 | 19 |
| Supermarkets | `/retail?shop_type=supermarket` | 200 | 150 (161 total reported) |
| Water taps | `/amenities?subcategory=water_tap` | 200 | 150 |
| Traffic | `/mobility/traffic` | 200 | 18 |
| Parking | `/mobility?subcategory=parking` | 200 | 7 |
| Bridges | `/mobility?subcategory=bridge` | 200 | 4 |
| Roadworks | `/mobility/roadworks` | 200 | 6 |
| City pulse | `/crowd/live` | 200 | 19 |
| Emergency reports | `/live?category=emergency` | 200 | 25 |
| Local news | `/live?category=news` | 200 | 83 |
| Environment | `/environment` | 200 | 5 |
| Cameras, after source repair | `/amenities/cameras` | 200 | 150 |
| Camera public-footage filter, after repair | `/amenities/cameras?has_live_feed=true` | 200 | 0 |
| Concerts | `/events?subcategory=concert` | 200 | 49 |
| Theatre | `/events?subcategory=theatre` | 200 | 6 |
| Festivals | `/events?subcategory=festival` | 200 | 11 |
| Exhibitions | `/events?subcategory=exhibition` | 200 | 1 |
| Football | `/events?subcategory=stadium_fixture` | 200 | 26 |
| Toilets | `/amenities?subcategory=toilet` | 200 | 28 |
| AEDs | `/amenities?subcategory=aed` | 200 | 115 |
| EV charging | `/amenities?subcategory=ev_charger` | 200 | 150 |
| Convenience shops | `/retail?shop_type=convenience` | 200 | 141 |
| Bakeries | `/retail?shop_type=bakery` | 200 | 99 |
| Pharmacies | `/retail?shop_type=pharmacy` | 200 | 68 |
| Coolsingel search (`q=Coolsingel&limit=8`) | `/search` | 200 | 8 |
| Centrum passport | `/living/districts/Rotterdam%20Centrum/passport` | 200 | 1 Feature |

A second read-only pass verified the geometry types used by the renderer:

| Geometry | Returned datasets at these bounds |
| --- | --- |
| `Point` | Events150, shops150, facilities150, parking7, bridges4, **roadworks6**, emergency reports25, news83, environment5, cameras150. |
| `LineString` | Traffic18. |
| `MultiPolygon` | Districts19 and city pulse19 (citywide). |

No missing or unexpected geometry was present in these responses. The roadworks
feed currently supplies point locations, so it belongs in the point-marker path.
After the final Python edits, `/health/live` returned HTTP 200 in approximately
1.9ms locally. A brief pause during Uvicorn development reload is separate from
feed availability; this measurement is not a production latency guarantee.

## Camera repair and ongoing ingestion

The replacement `camera_harvester.py` accepts explicit OpenStreetMap camera,
surveillance, CCTV or speed-camera tags. It does not infer cameras from venue
types, invent fallback devices, guess public footage URLs, or check external
streams during a client request. A provider failure preserves prior directory
records instead of fabricating a successful harvest. The generic amenities
camera job now calls this same pipeline, preventing the older synthetic fallback
from returning during a different scheduled job.

The repeatable repair retired **8,025** owned inferred, synthetic or duplicate
records in the local database. Records were marked inactive and retained for
audit; unrelated provider records were preserved. **778** OSM-backed mapped
locations remained active: 557 surveillance, 155 traffic and 66 in the legacy
ANPR/speed-camera category. The ANPR grouping is a map category, not verification
that every speed camera performs number-plate recognition.

A second repair run retired zero records and retained the same 778, confirming
idempotence on this dataset. A fresh strict harvest was attempted: both Overpass
mirrors timed out after 25 seconds each. The job reported `source_available=false`
and zero refreshed records, preserving the repaired OSM directory rather than
inventing a successful refresh or replacing it with guessed devices. These are
retained mapped locations, not fresh camera observations.

The repaired data carries these fields under `properties.details`:

| Field | Meaning |
| --- | --- |
| `source: "OpenStreetMap"` | Location provenance, not a live operational check. |
| `source_url` | Direct `https://www.openstreetmap.org/node/{osm_id}` source link. |
| `location_basis: "osm_camera_tag"` | A camera-related tag, rather than a shop/venue inference. |
| `feed_status: "not_provided"` | No verified public footage is supplied. |
| `has_live_feed: false` | A camera location does not imply a playable video feed. |
| `stream_url`, `snapshot_url` | Absent/null for these repaired records; guessed links were removed. |
| `source_updated_at` | OSM edit time when returned by a successful new source harvest; not a video timestamp. |

The frontend should default to all mapped camera locations and label the layer
as a directory. Zero public feeds is an honest empty result, not a backend outage.
The source link supports inspecting the mapped record. Directory retrieval time
does not make the camera currently operational, publicly viewable or independently
verified on the ground.

Run the same repair on a target deployment with its normal database/Redis
configuration, before exposing the new directory UI:

```sh
docker exec rotterdam_dev_api python scripts/repair_camera_directory.py
```

Use that deployment's actual API container name. The camera worker also calls the
idempotent repair before refreshing its OSM source. Restart the worker when deploying
the new code so its previous in-memory harvester cannot reintroduce inferred rows.
Only the local worker was restarted in this session; production was not changed.

## Validation

```sh
docker exec rotterdam_dev_api python -m pytest tests/test_map_filters.py tests/test_retail.py tests/test_api_endpoints.py tests/test_ingestion_parsers.py -q --tb=short
```

**27 passed.** The new camera tests use transactional temporary PostGIS tables,
so their edge cases never enter the shared map dataset. They cover disjoint camera
feed filters, composition with category/viewport filters, safe retirement and
deduplication, source preservation, rejection of venue-based camera inference,
and consistent HTTP 400 responses for invalid retail bounds. This scoped result
is separate from the frontend/browser suite and is not a full backend rerun.

The subsequent full backend run passed **111 tests**. Its district passport test
now compares the exact response with current database source rows rather than
freezing a housing count that changes during normal ingestion. The complete
frontend review also passed 14 unit/spatial checks and 23 browser checks, including
the actual built Docker preview's same-origin API connection. See
[`frontend-review/README.md`](frontend-review/README.md) for the final commands and screenshots.
