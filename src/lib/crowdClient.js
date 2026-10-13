/**
 * Rotterdam Live — /crowd Domain Client & Types (Svelte + MapLibre GL)
 * 
 * Production-Grade Crowdness Engine & Real-Time Forecaster (Platform v1.9.0)
 * Zero in-request computation invariant: queries pre-compiled sub-5ms Redis snapshots.
 * 
 * Provides typed access to:
 * - Master Live Crowdness GeoJSON: /api/v1/crowd/live
 * - District Crowd Passport & 24h Forecast: /api/v1/crowd/districts/{name}
 * - Multi-Horizon Forecast Matrix: /api/v1/crowd/forecast
 * - Telemetry History: /api/v1/crowd/history
 * - Municipal Overview Stats: /api/v1/crowd/overview
 */

import { API_BASE_URL } from './liveLayers.js';

export const CROWD_STATUS_COLORS = {
  quiet: '#10b981',       // Quiet (0-25) — Green
  moderate: '#06b6d4',    // Moderate (26-50) — Cyan
  busy: '#f59e0b',        // Busy (51-75) — Amber
  saturated: '#ef4444',   // Peak/Saturated (76-100) — Red
};

export const CROWD_COLOR_RAMP = [
  'interpolate',
  ['linear'],
  ['get', 'crowd_index'],
  0, '#10b981',
  25, '#10b981',
  26, '#06b6d4',
  50, '#06b6d4',
  51, '#f59e0b',
  75, '#f59e0b',
  76, '#ef4444',
  100, '#dc2626'
];

/**
 * Fetch master live crowdness GeoJSON FeatureCollection across all 19 districts.
 * @param {string} [baseUrl]
 * @returns {Promise<any|null>}
 */
export async function fetchLiveCrowdness(baseUrl = API_BASE_URL) {
  try {
    const res = await fetch(`${baseUrl}/api/v1/crowd/live`, {
      headers: { 'Accept': 'application/json' }
    });
    if (!res.ok) {
      console.warn(`[CrowdClient] /api/v1/crowd/live returned status ${res.status}`);
      return null;
    }
    return await res.json();
  } catch (err) {
    console.error('[CrowdClient] Failed to fetch live crowdness GeoJSON:', err);
    return null;
  }
}

/**
 * Fetch detailed single district crowd passport and 24h forecast series.
 * @param {string} districtName
 * @param {string} [baseUrl]
 * @returns {Promise<any|null>}
 */
export async function fetchDistrictCrowdProfile(districtName, baseUrl = API_BASE_URL) {
  try {
    const res = await fetch(`${baseUrl}/api/v1/crowd/districts/${encodeURIComponent(districtName)}`, {
      headers: { 'Accept': 'application/json' }
    });
    if (!res.ok) {
      console.warn(`[CrowdClient] Profile for '${districtName}' returned status ${res.status}`);
      return null;
    }
    return await res.json();
  } catch (err) {
    console.error(`[CrowdClient] Failed to fetch crowd profile for '${districtName}':`, err);
    return null;
  }
}

/**
 * Fetch multi-horizon forecast matrix across Rotterdam districts.
 * @param {string} [district]
 * @param {string} [baseUrl]
 * @returns {Promise<any|null>}
 */
export async function fetchCrowdForecast(district = '', baseUrl = API_BASE_URL) {
  try {
    const url = district
      ? `${baseUrl}/api/v1/crowd/forecast?district=${encodeURIComponent(district)}`
      : `${baseUrl}/api/v1/crowd/forecast`;
    const res = await fetch(url, {
      headers: { 'Accept': 'application/json' }
    });
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error('[CrowdClient] Failed to fetch crowd forecast:', err);
    return null;
  }
}

/**
 * Fetch crowd telemetry history from indexed historical table.
 * @param {string} [district]
 * @param {number} [hours=24]
 * @param {number} [limit=100]
 * @param {string} [baseUrl]
 * @returns {Promise<any|null>}
 */
export async function fetchCrowdHistory(district = '', hours = 24, limit = 100, baseUrl = API_BASE_URL) {
  try {
    const params = new URLSearchParams();
    if (district) params.append('district', district);
    params.append('hours', hours.toString());
    params.append('limit', limit.toString());

    const res = await fetch(`${baseUrl}/api/v1/crowd/history?${params.toString()}`, {
      headers: { 'Accept': 'application/json' }
    });
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error('[CrowdClient] Failed to fetch crowd history:', err);
    return null;
  }
}

/**
 * Fetch high-level municipal crowd overview stats.
 * @param {string} [baseUrl]
 * @returns {Promise<any|null>}
 */
export async function fetchCrowdOverview(baseUrl = API_BASE_URL) {
  try {
    const res = await fetch(`${baseUrl}/api/v1/crowd/overview`, {
      headers: { 'Accept': 'application/json' }
    });
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error('[CrowdClient] Failed to fetch crowd overview:', err);
    return null;
  }
}

/**
 * Install or update the interactive Crowdness Choropleth Layer on MapLibre GL.
 * @param {import('maplibre-gl').Map} map
 * @param {Object} [options]
 */
export async function installCrowdMapLayer(map, options = {}) {
  if (!map) return;

  const sourceId = 'rotterdam-crowd-source';
  const fillLayerId = 'rotterdam-crowd-fill';
  const lineLayerId = 'rotterdam-crowd-line';

  const data = await fetchLiveCrowdness();
  if (!data) return;

  if (map.getSource(sourceId)) {
    map.getSource(sourceId).setData(data);
    return;
  }

  map.addSource(sourceId, {
    type: 'geojson',
    data: data,
  });

  // Choropleth Fill Layer
  map.addLayer({
    id: fillLayerId,
    type: 'fill',
    source: sourceId,
    paint: {
      'fill-color': CROWD_COLOR_RAMP,
      'fill-opacity': options.opacity || 0.45,
    },
  });

  // District Boundary Outline Layer
  map.addLayer({
    id: lineLayerId,
    type: 'line',
    source: sourceId,
    paint: {
      'line-color': '#ffffff',
      'line-width': 1.5,
      'line-opacity': 0.7,
    },
  });
}
