# Live weather implementation — 28 October 2026

The weather HUD and controller have no presets or simulator API. Initially there
are no values or effects. A complete validated 12-node snapshot, solar position,
and explicit freshness status are required. Missing or failed requests display
unavailable/stale status rather than claiming live conditions. Stale values retain their
original valid time; cloud effects stop while stale. The HUD consistently reports
Rotterdam Centrum model conditions, including source and valid time.

Open-Meteo precipitation amounts are normalized using current.interval to mm/h
(and snowfall to cm/h). Missing or nonfinite upstream fields invalidate the grid.
The harvester retains its last successful snapshot for up to a day without
refreshing its timestamp, and returns stale status during outages. A cold outage
returns 503. Rain nowcast failures return unavailable/null or a labelled stale
snapshot, rather than a synthetic dry forecast. Local Buienradar clock times are
resolved to dated UTC timestamps. Station observations retain their source time;
observations older than 30 minutes are excluded from the unified current values.
Crowd weather integration reads nested rain/wind fields and preserves zeros.

Observed RainViewer raster tiles show rain geography with frame time and visible
source credit. As of 5 November, radar starts off: the Map panel's Rain radar
switch requests metadata/tiles only when enabled, independently of clouds.
Frames older than 20 minutes are removed. Maximum source zoom is
7; map overscaling provides no additional meteorological resolution. A metadata
frame timestamp is not the individual radar observation time. Rain streaks and
random lightning flashes have been removed. Clouds remain procedural illustrations
of model conditions; their placement and fixed heights are not satellite observations.
The final shader samples two continuous 3D density fields, with 16 depth samples
per deck and two probes toward the sun for self-shadowing. The lower volume combines
low/middle cover at illustrative heights 900–2400m; the upper uses high cover at
3000–3650m. Layered noise, erosion, transmission and solar/ambient lighting replace
the intermediate streak/sheet appearance. These heights, projections and cloud
shapes remain approximations. Both decks use model 10m wind, converted to km/s.
The card is charcoal with muted text and no simulator controls. Rendering uses a
reduced-resolution framebuffer; a 33ms idle timer is not a guarantee of 60 FPS.
The system reduced-motion preference freezes idle cloud advection. Explorer
overlays draw above the atmosphere; guarded custom-layer ordering prevents
recursive MapLibre style changes.

Local development uses Vite's API/health proxy to avoid localhost/127.0.0.1 CORS
mismatches. The local worker must restart when ingestion code changes. Production
must deploy backend, worker and frontend together; the older public API cannot
satisfy the new controller's required schema. This change was not deployed publicly.

Further accuracy work: evaluate direct KNMI spatial radar/nowcast access, satellite
cloud masks and cloud-level wind/height data, a regular model grid, station bias
correction validated at matched positions/times, and several weeks of forecast
verification. No claim of measured forecast accuracy is made by this implementation.

The full session explanation, cache/status contract, renderer details, validation
results and remaining limitations are recorded in the root
`rotterdam_live_api_architecture.txt` (architecture revision 2.7.0, updated
10 November with custom SVG map symbols, frontend polish and same-origin built
preview/API routing). The existing cloud renderer remains enabled on Aerial;
source freshness and model limitations are unchanged. Work is carried
on `malidev`, including the earlier feature-branch history. Production remains
unchanged by this development work.

The annotated UI follow-up moved the Rotterdam date/time into the weather card.
Its main button now collapses the whole card to a compact view and expands it
again, independently of cloud rendering. Bottom overlays and zoom/reset controls
were removed; map credits remain inside Map settings.

The NL/EN control localizes weather conditions using the model's weather codes.
The atmosphere renders on Aerial, and the dashboard reads the live model in
all three views. The selected cloud preference applies when returning to Aerial.
