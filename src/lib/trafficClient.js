/**
 * Rotterdam Live — /mobility/traffic Domain Client & MapLibre GL Integration
 * 
 * Platform v2.0.0-rc
 * Real-time traffic speeds, congestion tiers, travel times, and delays
 * along the Rotterdam Ring (A20, A16, A15, A4, A13) and Core Urban Arterials.
 * 
 * Architectural Invariant: Zero In-Request Computation.
 * Pre-compiled sub-5ms Redis snapshots with RFC 7232 ETag conditional caching.
 */

import maplibregl from 'maplibre-gl';
import { API_BASE_URL } from './liveLayers.js';

export const TRAFFIC_CONGESTION_COLORS = {
  free_flow: '#10b981',   // Emerald Green: speed >= 85% free flow
  moderate: '#f59e0b',    // Amber / Yellow: 60% <= speed < 85%
  heavy: '#f97316',       // Orange: 30% <= speed < 60%
  standstill: '#ef4444',  // Red: speed < 30%
};

export const TRAFFIC_COLOR_EXPRESSION = [
  'match',
  ['get', 'congestion_level'],
  'free_flow', '#10b981',
  'moderate', '#f59e0b',
  'heavy', '#f97316',
  'standstill', '#ef4444',
  '#10b981' // fallback
];

export const TRAFFIC_WIDTH_EXPRESSION = [
  'interpolate',
  ['linear'],
  ['zoom'],
  10, ['case', ['==', ['get', 'road_type'], 'motorway'], 3.5, 2.5],
  14, ['case', ['==', ['get', 'road_type'], 'motorway'], 6.0, 4.5],
  18, ['case', ['==', ['get', 'road_type'], 'motorway'], 9.0, 7.0]
];

export const TRAFFIC_CASING_WIDTH_EXPRESSION = [
  'interpolate',
  ['linear'],
  ['zoom'],
  10, ['case', ['==', ['get', 'road_type'], 'motorway'], 5.5, 4.0],
  14, ['case', ['==', ['get', 'road_type'], 'motorway'], 8.5, 6.5],
  18, ['case', ['==', ['get', 'road_type'], 'motorway'], 12.0, 9.5]
];

let trafficRefreshInterval = null;
let trafficPopup = null;
let lastTrafficETag = null;
let cachedTrafficData = null;

/**
 * Fetch live traffic GeoJSON FeatureCollection with optional filtering and ETag support.
 * @param {Object} [options]
 * @param {string} [options.road_type] - 'motorway' | 'urban_arterial'
 * @param {string} [options.congestion_level] - 'free_flow' | 'moderate' | 'heavy' | 'standstill'
 * @param {string} [options.district] - Rotterdam district
 * @param {string} [options.bbox] - 'minLon,minLat,maxLon,maxLat'
 * @param {string} [baseUrl]
 * @returns {Promise<any|null>}
 */
export async function fetchLiveTraffic(options = {}, baseUrl = API_BASE_URL) {
  try {
    const params = new URLSearchParams();
    if (options.road_type) params.append('road_type', options.road_type);
    if (options.congestion_level) params.append('congestion_level', options.congestion_level);
    if (options.district) params.append('district', options.district);
    if (options.bbox) params.append('bbox', options.bbox);

    const queryStr = params.toString() ? `?${params.toString()}` : '';
    const headers = { 'Accept': 'application/json' };
    
    // Pass ETag if available for conditional 304 caching
    if (!options.road_type && !options.congestion_level && !options.district && !options.bbox && lastTrafficETag) {
      headers['If-None-Match'] = lastTrafficETag;
    }

    const res = await fetch(`${baseUrl}/api/v1/mobility/traffic${queryStr}`, { headers });
    
    if (res.status === 304 && cachedTrafficData) {
      return cachedTrafficData;
    }

    if (!res.ok) {
      console.warn(`[TrafficClient] /api/v1/mobility/traffic returned status ${res.status}`);
      return null;
    }

    const newETag = res.headers.get('ETag');
    if (newETag && !queryStr) {
      lastTrafficETag = newETag;
    }

    const data = await res.json();
    if (!queryStr) {
      cachedTrafficData = data;
    }
    return data;
  } catch (err) {
    console.error('[TrafficClient] Failed to fetch live traffic:', err);
    return null;
  }
}

/**
 * Fetch high-level municipal traffic overview statistics.
 * @param {string} [baseUrl]
 * @returns {Promise<any|null>}
 */
export async function fetchTrafficOverview(baseUrl = API_BASE_URL) {
  try {
    const res = await fetch(`${baseUrl}/api/v1/mobility/traffic/overview`, {
      headers: { 'Accept': 'application/json' }
    });
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error('[TrafficClient] Failed to fetch traffic overview:', err);
    return null;
  }
}

/**
 * Fetch single traffic segment performance by corridor ID.
 * @param {string} segmentId
 * @param {string} [baseUrl]
 * @returns {Promise<any|null>}
 */
export async function fetchTrafficSegment(segmentId, baseUrl = API_BASE_URL) {
  try {
    const res = await fetch(`${baseUrl}/api/v1/mobility/traffic/${encodeURIComponent(segmentId)}`, {
      headers: { 'Accept': 'application/json' }
    });
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error(`[TrafficClient] Failed to fetch segment '${segmentId}':`, err);
    return null;
  }
}

/**
 * Install or update the interactive Real-Time Traffic vector layer on MapLibre GL.
 * @param {import('maplibre-gl').Map} map
 * @param {Object} [options]
 */
export async function installTrafficMapLayer(map, options = {}) {
  if (!map) return;

  const sourceId = 'rotterdam-traffic-source';
  const casingLayerId = 'rotterdam-traffic-casing';
  const lineLayerId = 'rotterdam-traffic-line';

  // 1. Fetch live GeoJSON traffic corridors
  const data = await fetchLiveTraffic(options);
  if (!data) return;

  // If source already exists, update data directly
  if (map.getSource(sourceId)) {
    map.getSource(sourceId).setData(data);
    return;
  }

  // 2. Add GeoJSON source with LineString geometries
  map.addSource(sourceId, {
    type: 'geojson',
    data: data,
  });

  // 3. Dark/Neutral casing halo layer for contrast against varied map styles
  map.addLayer({
    id: casingLayerId,
    type: 'line',
    source: sourceId,
    layout: {
      'line-join': 'round',
      'line-cap': 'round',
    },
    paint: {
      'line-color': '#0f172a',
      'line-width': TRAFFIC_CASING_WIDTH_EXPRESSION,
      'line-opacity': options.casingOpacity || 0.65,
    },
  });

  // 4. Main LineString Traffic Flow Layer
  map.addLayer({
    id: lineLayerId,
    type: 'line',
    source: sourceId,
    layout: {
      'line-join': 'round',
      'line-cap': 'round',
    },
    paint: {
      'line-color': TRAFFIC_COLOR_EXPRESSION,
      'line-width': TRAFFIC_WIDTH_EXPRESSION,
      'line-opacity': options.opacity || 0.95,
    },
  });

  // 5. Cursor styling on hover
  map.on('mouseenter', lineLayerId, () => {
    map.getCanvas().style.cursor = 'pointer';
  });

  map.on('mouseleave', lineLayerId, () => {
    map.getCanvas().style.cursor = '';
  });

  // 6. Interactive popup on segment click
  map.on('click', lineLayerId, (e) => {
    if (!e.features || !e.features[0]) return;
    const feat = e.features[0];
    const props = feat.properties;

    const level = props.congestion_level || 'free_flow';
    const color = TRAFFIC_CONGESTION_COLORS[level] || '#10b981';
    const speed = Math.round(Number(props.speed_kmh) || 0);
    const delaySec = Number(props.delay_seconds) || 0;
    const delayMin = Math.round(delaySec / 60);
    const travelTimeMin = Math.round((Number(props.current_travel_time_seconds) || 0) / 60);
    const freeFlowMin = Math.round((Number(props.free_flow_seconds) || 0) / 60);
    const roadType = props.road_type === 'motorway' ? 'Snelweg (Rijksweg)' : 'Stedelijke Hoofdas';

    const levelDutch = {
      free_flow: 'Vlotte doorstroming',
      moderate: 'Matige vertraging',
      heavy: 'Drukke file',
      standstill: 'Stilstaand verkeer'
    }[level] || level;

    const delayBadge = delaySec > 0 
      ? `<span style="background: ${color}20; color: ${color}; font-weight: 700; padding: 2px 6px; border-radius: 4px; font-size: 11px;">+${delayMin} min vertraging</span>`
      : `<span style="background: #10b98120; color: #10b981; font-weight: 700; padding: 2px 6px; border-radius: 4px; font-size: 11px;">Geen vertraging</span>`;

    const popupHtml = `
      <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; min-width: 240px; max-width: 300px; padding: 2px;">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
          <span style="background: ${color}; color: #ffffff; font-weight: 700; font-size: 10px; text-transform: uppercase; padding: 2px 6px; border-radius: 4px;">
            ${levelDutch}
          </span>
          <span style="font-size: 11px; color: #64748b; font-weight: 600;">
            ${props.district || 'Rotterdam'}
          </span>
        </div>
        <div style="font-size: 13px; font-weight: 700; color: #0f172a; line-height: 1.3; margin-bottom: 6px;">
          ${props.name}
        </div>
        <div style="margin-bottom: 6px;">
          ${delayBadge}
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px; background: #f8fafc; padding: 8px; border-radius: 6px; font-size: 11px; margin-bottom: 6px;">
          <div>
            <div style="color: #64748b;">Gem. Snelheid</div>
            <div style="font-size: 14px; font-weight: 700; color: #0f172a;">${speed} km/u</div>
          </div>
          <div>
            <div style="color: #64748b;">Reistijd</div>
            <div style="font-size: 14px; font-weight: 700; color: #0f172a;">${travelTimeMin} min <span style="font-size: 10px; color: #94a3b8;">(${freeFlowMin}m)</span></div>
          </div>
        </div>
        <div style="display: flex; justify-content: space-between; font-size: 10px; color: #94a3b8;">
          <span>${roadType}</span>
          <span>NDW Live Telemetrie</span>
        </div>
      </div>
    `;

    if (trafficPopup) trafficPopup.remove();

    trafficPopup = new maplibregl.Popup({ offset: 10, closeButton: true, maxWidth: '320px' })
      .setLngLat(e.lngLat)
      .setHTML(popupHtml)
      .addTo(map);
  });

  // 7. Periodic refresh loop (every 30 seconds)
  if (!trafficRefreshInterval) {
    trafficRefreshInterval = setInterval(async () => {
      const updated = await fetchLiveTraffic(options);
      if (updated && map.getSource(sourceId)) {
        map.getSource(sourceId).setData(updated);
      }
    }, 30000);
  }
}

/**
 * Toggle visibility of the traffic layers on MapLibre GL.
 * @param {import('maplibre-gl').Map} map
 * @param {boolean} visible
 */
export function setTrafficVisibility(map, visible) {
  if (!map) return;
  const val = visible ? 'visible' : 'none';
  if (map.getLayer('rotterdam-traffic-casing')) {
    map.setLayoutProperty('rotterdam-traffic-casing', 'visibility', val);
  }
  if (map.getLayer('rotterdam-traffic-line')) {
    map.setLayoutProperty('rotterdam-traffic-line', 'visibility', val);
  }
}
