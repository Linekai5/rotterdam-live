# Frontend review — 10 November 2026

Reviewed the running app, traced every selected layer through the API, and iterated on desktop/mobile screenshots. The implementation is local development on `malidev`; production was not deployed.

## Visual evidence

| Before | After |
| --- | --- |
| [Desktop](before-desktop.png) | [Desktop](after-desktop.jpg) |
| [Mobile](before-mobile.png) | [Mobile](after-mobile.jpg) |

[Selected bridge and detail sheet](after-detail.jpg) · [Map appearance](after-appearance.jpg) · [320px mobile](after-mobile-320.jpg) · [Custom map symbols](map-symbols.jpg)

These captures use real API data. Weather, event listings, the viewport and source update times can differ between captures; test weather presets are not used in the app.

## What changed and why

- Replaced the oversized serif introduction and inconsistent rounded controls with a compact typographic hierarchy, custom bridge identity, self-hosted Instrument Sans, graphite surfaces and clipped-corner icon plaques. Font source: [Google Fonts Instrument Sans](https://github.com/google/fonts/tree/main/ofl/instrumentsans); the OFL license is included under `web/public/fonts/`.
- Coordinated the moving tab rule, directional panel entry, expanding/collapsing filters, record reveals and map camera movement. Reduced motion disables decorative movement; no autoplay camera orbit was introduced.
- Shared original SVG paths between controls and map symbols. Different event types, bridges, cameras, parking and facilities now have identifiable glyphs. Category/subtype cluster plaques retain counts; selected glyphs use brackets. Sprites decode only when needed and survive style changes.
- Added hover previews, stronger selected-record metrics, category navigation and a conditional scroll cue. Mobile switch hit areas and close controls were expanded; 1512/1200/390/320px layouts were checked for overlap and overflow.
- Fixed MapLibre getter-backed geometry being lost when copying selected features. Clicking a map glyph now retains its location and the Show on map action.
- Added source-backed camera locations and fixed camera/retail filter contracts. Removed inferred cameras and guessed public streams. See [the API/source audit](../map_feed_audit.md) for repair evidence and source limits.
- Fixed built localhost API traffic bypassing the serving origin and failing CORS on 8080. A shared API base and Docker Nginx proxy now align 5173 and 8080 with the API on 8000.
- Preserved default live clouds on Aerial, optional radar, two concurrent explorer requests, viewport limits, cancellation, visible failures/retry and no optional startup fetches.

## Verification

| Check | Result |
| --- | --- |
| `docker exec rotterdam_dev_api python -m pytest -q` | 111 passed |
| `npm --prefix web test` | 14 passed |
| `WEB_PREVIEW_ORIGIN=http://localhost:8080 npm --prefix web run test:browser` | 23 passed |
| `npm --prefix web run build` | Passed |
| `docker compose up -d --no-deps --build web` | Built and started local preview |
| Actual UI layer audit | All 13 selected layers loaded; no captured HTTP errors or uncaught page errors; zero optional initial requests |

The built-preview test is explicitly skipped if `WEB_PREVIEW_ORIGIN` is unset, since it requires the Docker web/API stack. Existing backend passport assertions now compare exact response values with their database source rows, rather than a frozen housing count that ingestion legitimately changes.

The current camera source supplies mapped locations, not verified public video. Its Overpass refresh timed out during review and retained prior sourced records. Other feeds may return empty results for a time window, filter or viewport; a successful refresh does not independently verify physical conditions. Rendering speed still depends on device, tiles and weather load; no universal frame-rate guarantee is claimed.
