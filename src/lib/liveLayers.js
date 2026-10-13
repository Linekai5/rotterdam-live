import maplibregl from 'maplibre-gl';

/**
 * Live PostGIS Layer Integration for Rotterdam Live
 */

const DEFAULT_API_BASE = typeof window !== 'undefined' 
  ? (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
      ? 'http://localhost:8000'
      : `${window.location.protocol}//${window.location.hostname}:8000`)
  : 'http://localhost:8000';

export const API_BASE_URL = (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL) || DEFAULT_API_BASE;

export const CATEGORY_COLORS = {
  emergency: '#ef4444',    // Bright Red
  mobility: '#3b82f6',     // Bright Blue (garages, bridges, transit)
  environment: '#10b981',  // Emerald Green (air quality, weather)
  news: '#f59e0b',         // Warm Amber (civic alerts, news)
  event: '#ec4899',        // Vibrant Pink (Ticketmaster, festivals, stadium fixtures)
  default: '#8b5cf6'       // Purple fallback
};

let refreshInterval = null;
let currentPopup = null;

/**
 * Fetch canonical GeoJSON FeatureCollection from PostGIS backend
 */
export async function fetchLiveEvents(baseUrl = API_BASE_URL) {
  try {
    const res = await fetch(`${baseUrl}/api/v1/live?limit=300&active_only=true`, {
      headers: { 'Accept': 'application/json' }
    });
    if (!res.ok) {
      console.warn(`[LiveEvents] API returned status ${res.status}`);
      return null;
    }
    return await res.json();
  } catch (err) {
    console.error('[LiveEvents] Failed to fetch live data from PostGIS backend:', err);
    return null;
  }
}

/**
 * Install or re-attach the PostGIS live events layers to MapLibre
 */
export async function installLiveEvents(map, options = {}) {
  if (!map) return;

  const sourceId = 'rotterdam-live-events';
  const glowLayerId = 'live-events-glow';
  const coreLayerId = 'live-events-core';

  // 1. Fetch initial data
  const geojson = await fetchLiveEvents();

  // If layers already exist, just update data
  if (map.getSource(sourceId)) {
    if (geojson) {
      map.getSource(sourceId).setData(geojson);
    }
    return;
  }

  // 2. Add GeoJSON source with clustering optional or unclustered points
  map.addSource(sourceId, {
    type: 'geojson',
    data: geojson || { type: 'FeatureCollection', features: [] }
  });

  // 3. Outer glowing halo layer (scaled by severity)
  map.addLayer({
    id: glowLayerId,
    type: 'circle',
    source: sourceId,
    paint: {
      'circle-radius': [
        'interpolate', ['linear'], ['coalesce', ['get', 'severity'], 1],
        1, 9,
        2, 12,
        3, 16,
        4, 20,
        5, 26
      ],
      'circle-color': [
        'match', ['get', 'category'],
        'emergency', CATEGORY_COLORS.emergency,
        'mobility', CATEGORY_COLORS.mobility,
        'environment', CATEGORY_COLORS.environment,
        'news', CATEGORY_COLORS.news,
        'event', CATEGORY_COLORS.event,
        CATEGORY_COLORS.default
      ],
      'circle-opacity': 0.28,
      'circle-blur': 0.4
    }
  });

  // 4. Core solid icon circle
  map.addLayer({
    id: coreLayerId,
    type: 'circle',
    source: sourceId,
    paint: {
      'circle-radius': [
        'interpolate', ['linear'], ['coalesce', ['get', 'severity'], 1],
        1, 5,
        2, 6.5,
        3, 8.5,
        4, 11,
        5, 14
      ],
      'circle-color': [
        'match', ['get', 'category'],
        'emergency', CATEGORY_COLORS.emergency,
        'mobility', CATEGORY_COLORS.mobility,
        'environment', CATEGORY_COLORS.environment,
        'news', CATEGORY_COLORS.news,
        'event', CATEGORY_COLORS.event,
        CATEGORY_COLORS.default
      ],
      'circle-stroke-width': 1.5,
      'circle-stroke-color': '#ffffff',
      'circle-opacity': 0.95
    }
  });

  // 5. Cursor styling on hover
  map.on('mouseenter', coreLayerId, () => {
    map.getCanvas().style.cursor = 'pointer';
  });
  map.on('mouseleave', coreLayerId, () => {
    map.getCanvas().style.cursor = '';
  });

  // 6. Interactive Click Popup
  map.on('click', coreLayerId, (e) => {
    if (!e.features || !e.features.length) return;
    const feature = e.features[0];
    const coords = feature.geometry.coordinates.slice();
    const props = feature.properties || {};

    let details = {};
    try {
      details = typeof props.details === 'string' ? JSON.parse(props.details) : (props.details || {});
    } catch (_) {}

    const category = props.category || 'general';
    const subcategory = props.subcategory || '';
    const district = props.district || 'Rotterdam';
    const title = props.title || 'Live Incident / Event';
    const severity = props.severity || 1;
    const color = CATEGORY_COLORS[category] || '#6366f1';

    let extraHtml = '';

    // Parking details
    if (subcategory === 'parking' && details.available_spaces !== undefined) {
      extraHtml = `
        <div style="margin-top: 6px; display: grid; grid-template-columns: 1fr 1fr; gap: 4px; font-size: 11px;">
          <div><strong>Vrij:</strong> <span style="color: #10b981; font-weight: 700;">${details.available_spaces}</span></div>
          <div><strong>Capaciteit:</strong> ${details.total_capacity || 'N/A'}</div>
          <div><strong>Bezetting:</strong> ${details.occupancy_rate ? details.occupancy_rate + '%' : 'N/A'}</div>
          <div><strong>Status:</strong> ${details.status || 'OPEN'}</div>
        </div>
      `;
    } 
    // Air Quality details
    else if (subcategory === 'air_quality') {
      extraHtml = `
        <div style="margin-top: 6px; display: grid; grid-template-columns: 1fr 1fr; gap: 4px; font-size: 11px;">
          <div><strong>Luchtkwaliteit:</strong> <span style="color: #10b981;">${details.air_quality_label || 'Goed'}</span></div>
          <div><strong>Station:</strong> ${details.station_name || 'Rotterdam'}</div>
          <div><strong>PM2.5:</strong> ${details.pm25 ? details.pm25 + ' µg/m³' : 'N/A'}</div>
          <div><strong>NO2:</strong> ${details.no2 ? details.no2 + ' µg/m³' : 'N/A'}</div>
        </div>
      `;
    }
    // Bridge status
    else if (subcategory === 'bridge') {
      const isClosed = details.status === 'CLOSED';
      extraHtml = `
        <div style="margin-top: 6px; font-size: 11px;">
          <div><strong>Status:</strong> ${isClosed ? '<span style="color:#10b981;">Begaanbaar voor verkeer</span>' : '<span style="color:#ef4444;">Brug is geopend</span>'}</div>
        </div>
      `;
    }
    // P2000 emergency
    else if (category === 'emergency') {
      extraHtml = `
        <div style="margin-top: 6px; font-size: 11px; color: #4b5563;">
          <div><strong>Prioriteit:</strong> Prio ${details.prio || 1}</div>
          <div><strong>Dienst:</strong> ${subcategory.toUpperCase()}</div>
        </div>
      `;
    }
    // Event details
    else if (category === 'event') {
      const venue = details.venue_name || '';
      const src = details.source || '';
      const price = details.price_min ? `€${details.price_min}${details.price_max ? ' - €' + details.price_max : ''}` : '';
      const ticketUrl = details.ticket_url || '';
      extraHtml = `
        <div style="margin-top: 6px; font-size: 11px; line-height: 1.4;">
          ${venue ? `<div><strong>Locatie:</strong> ${venue}</div>` : ''}
          ${price ? `<div><strong>Prijs:</strong> ${price}</div>` : ''}
          ${src ? `<div><strong>Bron:</strong> <span style="text-transform: capitalize;">${src.replace('_', ' ')}</span></div>` : ''}
          ${ticketUrl ? `<div style="margin-top: 5px;"><a href="${ticketUrl}" target="_blank" rel="noopener noreferrer" style="display: inline-block; background: #ec4899; color: #fff; padding: 2px 8px; border-radius: 4px; font-weight: 600; text-decoration: none; font-size: 10px;">Tickets & Info →</a></div>` : ''}
        </div>
      `;
    }

    const popupHtml = `
      <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; min-width: 220px; max-width: 280px; padding: 2px;">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
          <span style="background: ${color}20; color: ${color}; font-weight: 700; font-size: 10px; text-transform: uppercase; padding: 2px 6px; border-radius: 4px; border: 1px solid ${color}40;">
            ${category} · ${subcategory}
          </span>
          <span style="font-size: 10px; color: #6b7280; font-weight: 600;">
            ${district}
          </span>
        </div>
        <div style="font-size: 13px; font-weight: 700; color: #111827; line-height: 1.3; margin-bottom: 4px;">
          ${title}
        </div>
        ${extraHtml}
        <div style="margin-top: 8px; font-size: 9px; color: #9ca3af; text-align: right;">
          Severity: ${severity}/5 · PostGIS Live
        </div>
      </div>
    `;

    if (currentPopup) currentPopup.remove();

    currentPopup = new maplibregl.Popup({ offset: 12, closeButton: true, maxWidth: '320px' })
      .setLngLat(coords)
      .setHTML(popupHtml)
      .addTo(map);
  });

  // 7. Setup automatic background refresh every 30 seconds
  if (!refreshInterval) {
    refreshInterval = setInterval(async () => {
      const updated = await fetchLiveEvents();
      if (updated && map.getSource(sourceId)) {
        map.getSource(sourceId).setData(updated);
      }
    }, 30000);
  }
}

/**
 * Filter visible live event categories on the map
 */
export function filterLiveEvents(map, activeCategories = ['emergency', 'mobility', 'environment', 'news']) {
  if (!map) return;
  const filterExpr = ['in', ['get', 'category'], ['literal', activeCategories]];
  if (map.getLayer('live-events-glow')) {
    map.setFilter('live-events-glow', filterExpr);
  }
  if (map.getLayer('live-events-core')) {
    map.setFilter('live-events-core', filterExpr);
  }
}
