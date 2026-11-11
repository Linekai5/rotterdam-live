# Rotterdam Live

[![CI](https://github.com/Linekai5/rotterdam-live/actions/workflows/ci.yml/badge.svg)](https://github.com/Linekai5/rotterdam-live/actions/workflows/ci.yml)

An interactive map of Rotterdam built with Svelte, MapLibre GL and Vite. Explore
city layers with custom map symbols, switch between Aerial, Night and Atlas,
and use the interface in Dutch or English.

The weather dashboard reads live API data. The clouds over Aerial are an
illustration driven by a weather model, rather than a live satellite cloud image.
Night and Atlas omit that atmosphere. Optional map layers load on demand.

## Run the frontend

Use Node.js 20.19+ or a supported newer release, and npm.

```bash
git clone https://github.com/Linekai5/rotterdam-live.git
cd rotterdam-live
npm ci
npm run dev
```

Open [localhost:5173](http://localhost:5173). The map loads public imagery;
weather, search and city feeds require an authorized Rotterdam Live API.
Vite forwards `/api` and `/health` to a separately running service at
`http://localhost:8000`. Missing feeds show their unavailable state.

`VITE_API_BASE_URL` can point the frontend at another authorized API. Set it in
an ignored `web/.env.local`; a cross-origin API must allow the frontend origin.
Vite variables are included in the browser bundle, so they must never contain
private credentials.

```bash
npm test
npm run build
# Browser checks require local Google Chrome and the private API for live-feed tests.
npm --prefix web run test:browser
python3 scripts/check-public-tree.py
```

## Repository layout

- `web/`: frontend source, original artwork, map data, tests and public assets.
- `docs/`: architecture notes and frontend review artifacts.
- `scripts/check-public-tree.py`: checks tracked files for private paths,
  IP literals in documentation, and common credential patterns.
- `nginx/` and `docker-compose*.yml`: deployment templates for maintainers.

The backend under `api/` is private and ignored in full. It must be supplied
separately to use the Docker stacks; a public clone can build the frontend
without it. Database credentials and production bind addresses belong in an
ignored root `.env`, using `.env.example` as a template. Existing database
credentials must match the stored database; changing the environment alone
does not rotate a database password.

Production automation is maintained privately. Public CI uses GitHub-hosted
runners to check the public tree, test/build the frontend and validate Nginx.

## Publication status

Both branch histories have been sanitized. Old pull-request references and
cached commit views still require GitHub Support cleanup. Publication was
requested with that cleanup outstanding. Actions are enabled for validation; no self-hosted runners are attached.
Production checks main every minute through a private host service; see
[deployment operations](docs/deployment.md). Read [the publication notes](docs/publication.md) before
updating an existing deployment checkout. Public visibility
exposes every branch, including `malidev`.

## Map data and credits

Imagery comes from PDOK / Samenwerkingsverband Beeldmateriaal, with vector data
from OpenStreetMap and OpenFreeMap. Provider credits and links are available
in the map's appearance settings. See [the frontend notes](web/README.md) and
[weather notes](docs/artifacts/live_weather.md) for implementation details.
