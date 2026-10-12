import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import styleClean from './style_clean.json';
import styleSatellite from './style_satellite.json';
import styleDark from './style_dark.json';
import { installCoastalOcean, removeCoastalOcean, OCEAN_LAYER } from './coastalOcean.js';
import { installLiveEvents, filterLiveEvents } from './liveLayers.js';

export { installLiveEvents, filterLiveEvents };

/**
 * Rotterdam coordinate bounding box [SW, NE]
 */
export const ROTTERDAM_BOUNDS = [
  [4.379, 51.861],
  [4.602, 51.995]
];

export const STYLE_CONFIGS = {
  clean: {
    id: 'clean',
    name: 'Clean Map',
    subtitle: 'Vector Positron',
    bgColor: '#c2c8ca',
    style: styleClean
  },
  satellite: {
    id: 'satellite',
    name: 'Satellite',
    subtitle: 'PDOK Aerial · 2026',
    bgColor: '#082632',
    style: styleSatellite
  },
  dark: {
    id: 'dark',
    name: 'Dark Night',
    subtitle: 'Vector Dark',
    bgColor: '#0c0c0c',
    style: styleDark
  }
};

export async function initMap(mapElement, onReady) {
  // Update live planet endpoints in background (non-blocking)
  fetch('https://tiles.openfreemap.org/planet')
    .then(res => res.ok ? res.json() : null)
    .then(data => {
      if (data?.tiles?.length) {
        Object.values(STYLE_CONFIGS).forEach(cfg => {
          if (cfg.style?.sources?.openmaptiles) {
            cfg.style.sources.openmaptiles.tiles = data.tiles;
          }
        });
      }
    })
    .catch(err => console.warn('Using bundled vector tiles URL', err));

  const urlParams = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null;
  const initialMode = urlParams?.get('mode') || 'satellite';
  const initialZoom = urlParams?.has('zoom') ? parseFloat(urlParams.get('zoom')) : null;
  const config = STYLE_CONFIGS[initialMode] || STYLE_CONFIGS.satellite;

  // Ensure container has valid rendered layout dimensions before constructing Map
  if (mapElement && (mapElement.clientWidth < 10 || mapElement.clientHeight < 10)) {
    await new Promise(resolve => {
      let attempts = 0;
      const check = () => {
        attempts++;
        if ((mapElement.clientWidth >= 10 && mapElement.clientHeight >= 10) || attempts > 50) {
          resolve();
        } else {
          requestAnimationFrame(check);
        }
      };
      requestAnimationFrame(check);
    });
  }

  const pageOrigin = typeof window !== 'undefined' ? window.location.origin : (typeof location !== 'undefined' ? location.origin : '');

  const map = new maplibregl.Map({
    container: mapElement,
    style: config.style,
    center: [4.48, 51.92],
    zoom: initialZoom || 12,
    minZoom: 8,
    maxZoom: 20,
    interactive: true,
    dragPan: true,
    scrollZoom: true,
    doubleClickZoom: true,
    touchZoomRotate: true,
    dragRotate: true,
    touchPitch: true,
    pitchWithRotate: true,
    maxPitch: 65,
    antialias: true,
    renderWorldCopies: false,
    attributionControl: true,
    maxTileCacheSize: 500,
    fadeDuration: 0,
    transformRequest: (url, resourceType) => {
      if (resourceType === 'Tile') {
        // Route vector tiles to local pre-downloaded tiles (z0-z14)
        const vectorMatch = url.match(/\/(\d+)\/(\d+)\/(\d+)\.pbf/);
        if (vectorMatch) {
          const z = parseInt(vectorMatch[1], 10);
          if (z <= 14) {
            return { url: `${pageOrigin}/tiles/vector/${z}/${vectorMatch[2]}/${vectorMatch[3]}.pbf` };
          }
        }
        // Route PDOK satellite tiles to local pre-downloaded tiles (z12-z15)
        const satMatch = url.match(/\/(\d+)\/(\d+)\/(\d+)\.jpeg/);
        if (satMatch) {
          const z = parseInt(satMatch[1], 10);
          if (z >= 12 && z <= 15) {
            return { url: `${pageOrigin}/tiles/satellite/${z}/${satMatch[2]}/${satMatch[3]}.jpeg` };
          }
        }
      }
      return { url };
    }
  });

  if (typeof window !== 'undefined') window.map = map;

  installCoastalOcean(map);

  map.on('load', () => {
    try { map.resize(); } catch (e) {}
    if (!initialZoom) {
      const c = map.getContainer();
      if (c && c.clientWidth > 160 && c.clientHeight > 160) {
        map.fitBounds(ROTTERDAM_BOUNDS, { padding: 40, animate: false });
      }
    }
    installLiveEvents(map);
    if (onReady) onReady(map);
  });

  try {
    const container = map.getContainer();
    container.style.transition = 'background-color 0.5s ease';
    container.style.backgroundColor = config.bgColor;
  } catch (e) {}

  return map;
}

export function switchStyle(map, mode, state = {}) {
  const config = STYLE_CONFIGS[mode];
  if (!config || !map) return;

  // Use diff: true to prevent reload flicker and preserve camera position
  removeCoastalOcean(map);
  map.setStyle(config.style, { diff: true });

  const container = map.getContainer();
  if (container) {
    container.style.backgroundColor = config.bgColor;
  }

  // Restore detail preferences after the new style is available.
  map.once('styledata', () => {
    if (state.labels === false) {
      toggleLabels(map, false);
    }
    if (state.buildings3d) {
      toggle3DBuildings(map, true);
    }
    installLiveEvents(map);
  });
}

export function toggleLabels(map, visible) {
  if (!map) return;
  const style = map.getStyle();
  if (!style || !style.layers) return;
  const visibility = visible ? 'visible' : 'none';
  style.layers.forEach(l => {
    if (l.type === 'symbol') {
      try {
        map.setLayoutProperty(l.id, 'visibility', visibility);
      } catch (e) {}
    }
  });
}

export function toggle3DBuildings(map, enabled) {
  if (!map) return;
  const layerId = '3d-buildings-extrusion';
  if (enabled) {
    if (!map.getLayer(layerId)) {
      try {
        const beforeLayer = map.getLayer(OCEAN_LAYER)
          ? OCEAN_LAYER
          : (map.getLayer('rotterdam-water-mask') ? 'rotterdam-water-mask' : undefined);
        map.addLayer({
          id: layerId,
          source: 'openmaptiles',
          'source-layer': 'building',
          type: 'fill-extrusion',
          minzoom: 13,
          paint: {
            'fill-extrusion-color': '#adb5bd',
            'fill-extrusion-height': ['coalesce', ['get', 'render_height'], 10],
            'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0],
            'fill-extrusion-opacity': 0.85
          }
        }, beforeLayer);
      } catch (e) {}
    } else {
      try {
        map.setLayoutProperty(layerId, 'visibility', 'visible');
      } catch (e) {}
    }
  } else {
    if (map.getLayer(layerId)) {
      try {
        map.setLayoutProperty(layerId, 'visibility', 'none');
      } catch (e) {}
    }
  }
}

export function resetView(map) {
  if (!map) return;
  map.fitBounds(ROTTERDAM_BOUNDS, { padding: 40, duration: 800 });
}
