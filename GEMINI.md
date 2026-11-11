# Rotterdam Live — Global Workspace Guidelines & Knowledge Base

## 1. Project Context & Production Architecture
* **Platform:** Rotterdam Live (`rotterdam-live`) — Real-time situational & geospatial platform for the Municipality of Rotterdam (`0599`).
* **Production Host:** Hetzner Cloud Linux VPS (`${PUBLIC_BIND_ADDRESS}` / Tailscale `${PRIVATE_BIND_ADDRESS}`, SSH port 2299).
* **Stack:**
  - **Reverse Proxy:** `rotterdam_live_nginx` (Public HTTPS: `rotterdamlive.nl`, Private Tailscale: `api.rotterdamlive.nl` over HTTP).
  - **Backend API:** `rotterdam_live_api` (FastAPI / Uvicorn, port 8000).
  - **Worker Daemon:** `rotterdam_live_worker` (16 background ingestion harvesters).
  - **Frontend Web:** `rotterdam_live_web` (Svelte 5, MapLibre GL JS, Vite).
  - **Spatial Database:** `rotterdam_live_db` (PostgreSQL 16 + PostGIS 3.4, persistent volume `rotterdam_live_pgdata`).
  - **Cache Layer:** `rotterdam_live_redis` (Redis 7 Alpine, sub-5ms SLA, persistent volume `rotterdam_live_redisdata`).
  - **SSL Renewal:** `rotterdam_live_certbot` (Let's Encrypt automated HTTP-01 renewal loop).
  - **CI/CD:** GitHub-hosted public-tree, frontend and Nginx checks. Backend source and deployment automation are supplied privately; no automatic deployment workflow is tracked.

## 2. Global Artifacts System Across All Sessions
All master architecture artifacts, operational runbooks, and design specifications are stored globally and persistent across all sessions:
* **Global Permanent Directory:** `/home/homeaccount/.gemini/global_artifacts/`
* **Repository Documentation:** `/home/homeaccount/rotterdam-live/docs/artifacts/`
* **Automatic Synchronization:**
  - On `SessionStart`, a lifecycle hook (`~/.gemini/config/scripts/sync_artifacts.py`) automatically populates the active session's artifact directory (`<appDataDir>/brain/<conversation-id>/`) from `/home/homeaccount/.gemini/global_artifacts/`.
  - When creating or modifying any artifact with `write_to_file`, always ensure the artifact is mirrored to `/home/homeaccount/.gemini/global_artifacts/` and `/home/homeaccount/rotterdam-live/docs/artifacts/` so it remains visible in all future sessions and in Git.

## 3. Key Invariants
1. **Sub-30ms GeoJSON SLA:** Never run spatial computations, external API calls, or LineString operations inside client HTTP requests. Rely on Redis caches and PostGIS GiST indexes.
2. **Strict Network Isolation:** Serve `rotterdamlive.nl` over public HTTPS with genuine Let's Encrypt TLS. Keep `api.rotterdamlive.nl` private over Tailscale HTTP with `Strict-Transport-Security: max-age=0`.

## 4. Public Source Boundary
The entire `api/` directory and machine-specific automation are ignored and untracked. Preserve local copies. Do not force-add private files or restore production addresses to documentation. Existing history remains private until a clean publication strategy is completed; see `docs/publication.md`.
