# ROF Vector Map

Satellite mode uses PDOK's fixed-year `2026_orthoHR` aerial imagery, with
256-pixel Web Mercator tiles through tile zoom 21. The map camera remains capped
at zoom 20: MapLibre already requests level-21 tiles there, and a camera zoom of
21 only magnifies them. Neutral contrast and saturation preserve the imagery's
shadow detail; linear resampling smooths magnification. The year is deliberately
pinned so annual imagery updates cannot silently change the river colors.

The responsive attribution control credits Samenwerkingsverband Beeldmateriaal,
PDOK, the CC BY 4.0 license, and OpenStreetMap/OpenFreeMap. Existing 3D controls
remain unchanged and off by default.

Satellite mode renders the surrounding ocean with an untiled WebGL mesh. The
supplied Rotterdam boundary is the precise hole in that mesh; it is independent
of the gradient texture's resolution. Water starts at `#495853` and continuously
transitions to `#082632` within 3.2 km. There are no tiled coastal polygons or
screen-pixel-width shoreline strokes.

The shoreline color in `src/lib/ocean-palette.json` is sampled from clear water
near the western Nieuwe Maas outlet in the 2026 imagery. Both the exterior
gradient and the interior water blend use it, replacing the former ArcGIS olive
tone. Review this palette whenever changing imagery year or color grading.

The 16-bit distance field is generated from the boundary in local Mercator
coordinates, scaled to metres at Rotterdam's latitude. A short interior blend
joins river imagery to the coast color: it is restricted to surveyed river water,
inset 8 metres from the banks, and fades out within 180 metres. The source water
polygons in `data/river-water.json` come from OpenFreeMap / OpenStreetMap. Small
differences between that survey and the satellite imagery may remain at banks.
The blend includes large lake-classified harbor areas that meet the city edge,
as well as rivers, to avoid hard cuts through connected water.

After editing `src/lib/rotterdam_boundary.json`, regenerate the derived assets:

```bash
npm run generate:ocean
npm test
npm run test:browser
npm run build
```

Browser tests use locally installed Google Chrome. They supply deterministic
imagery to check ocean color, city visibility, zooms 8–20, rotation/pitch, style
switching, and WebGL context restoration. Normal development uses live satellite
imagery; open `http://localhost:5173/?mode=satellite&zoom=11` to inspect it.

`coastalOcean.js` owns the custom layers and GPU resources. The original blue
GeoJSON mask remains only as a loading/error fallback. Historical halo JSON and
water-image assets are no longer used by the satellite style.

Clean, standalone Svelte vector map component using [MapLibre GL](https://maplibre.org/).
All transit layers, routes, stops, and vehicle tracking logic have been removed.

## 🚀 Quick Start (Run Standalone)

```bash
cd ~/Downloads/rofmap
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 📦 Using in Your Existing Svelte / SvelteKit App

Copy `src/lib/MapComponent.svelte` and `src/lib/map.js` into your project:

```svelte
<script>
  import MapComponent from '$lib/MapComponent.svelte';
</script>

<!-- Default: Rotterdam, Dark Vector Style -->
<MapComponent />

<!-- Or customize coordinates and style -->
<MapComponent 
  center={[4.47917, 51.9225]} 
  zoom={12} 
  style="https://tiles.openfreemap.org/styles/dark" 
/>
```

Make sure `maplibre-gl` is installed in your project:
```bash
npm install maplibre-gl
```

---

## 🗺️ Free Vector Styles (No API Key Required!)

The map uses **OpenFreeMap**, an open-source vector tile service that is **100% free with no registration or API key**:

| Style | URL |
| :--- | :--- |
| **Dark** | `https://tiles.openfreemap.org/styles/dark` |
| **Liberty** | `https://tiles.openfreemap.org/styles/liberty` |
| **Positron** (Light) | `https://tiles.openfreemap.org/styles/positron` |
| **Bright** | `https://tiles.openfreemap.org/styles/bright` |

---

## 📁 Directory Structure

```
rofmap/
├── README.md
├── package.json
├── vite.config.js
├── index.html
└── src/
    ├── App.svelte                # Root showcase component
    ├── main.js                   # Application entry point
    └── lib/
        ├── MapComponent.svelte   # Standalone Svelte map component
        └── map.js                # MapLibre GL setup & initialization
```
