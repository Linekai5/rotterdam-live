/**
 * Rotterdam Live — /events Domain Client & Types (Svelte + MapLibre GL)
 * 
 * Provides typed access to:
 * - Rotterdam Events: /api/v1/events
 * - Verified Venues: /api/v1/events/venues
 * - Municipal Festivals: /api/v1/events/festivals
 * - Stadium Fixtures: /api/v1/events/stadiums
 * - Event Statistics: /api/v1/events/stats
 * - Single Event Detail: /api/v1/events/{id}
 */

import { API_BASE_URL } from './liveLayers.js';

/**
 * @typedef {Object} EventVenue
 * @property {string} name
 * @property {string|null} [address]
 * @property {string|null} [postal_code]
 * @property {string} city
 * @property {string|null} [district]
 * @property {number[]} [coordinates] - [longitude, latitude] (GeoJSON order)
 * @property {number|null} [latitude] - Explicit WGS84 latitude
 * @property {number|null} [longitude] - Explicit WGS84 longitude
 */

/**
 * @typedef {Object} EventPrice
 * @property {number|null} [min]
 * @property {number|null} [max]
 * @property {string} currency
 */

/**
 * @typedef {Object} RotterdamEventProperties
 * @property {string} id
 * @property {string} title
 * @property {string|null} [description]
 * @property {string} category - "event"
 * @property {string} subcategory - concert, stadium_fixture, festival, theatre, comedy, sports, cultural, exhibition
 * @property {string} source - ticketmaster, stadium_fixtures, municipal_festivals, open_agenda
 * @property {EventVenue} venue
 * @property {string} start_time
 * @property {string|null} [end_time]
 * @property {string} district
 * @property {EventPrice|null} [price]
 * @property {string|null} [ticket_url]
 * @property {string|null} [image_url]
 * @property {string} status
 * @property {Record<string, any>} details
 */

/**
 * @typedef {Object} RotterdamEventFeature
 * @property {"Feature"} type
 * @property {{type: "Point", coordinates: number[]}} geometry
 * @property {RotterdamEventProperties} properties
 */

/**
 * @typedef {Object} RotterdamEventFeatureCollection
 * @property {"FeatureCollection"} type
 * @property {RotterdamEventFeature[]} features
 * @property {number} [total_count]
 */

/**
 * @typedef {Object} VenueSummary
 * @property {string} name
 * @property {string|null} [address]
 * @property {string} district
 * @property {number[]} coordinates - [longitude, latitude]
 * @property {number} total_events
 * @property {string[]} subcategories
 */

/**
 * @typedef {Object} EventStats
 * @property {number} total_events
 * @property {Record<string, number>} subcategories
 * @property {Record<string, number>} sources
 * @property {Record<string, number>} districts
 * @property {Record<string, number>} top_venues
 * @property {string} timestamp
 */

/**
 * Fetch events with optional filtering.
 * @param {Object} [params]
 * @param {string} [params.subcategory]
 * @param {string} [params.source]
 * @param {string} [params.district]
 * @param {string} [params.venue]
 * @param {string} [params.q]
 * @param {string} [params.date_from]
 * @param {string} [params.date_to]
 * @param {number[]} [params.bbox]
 * @param {number} [params.limit=100]
 * @param {number} [params.offset=0]
 * @returns {Promise<RotterdamEventFeatureCollection|null>}
 */
export async function fetchEvents(params = {}) {
  try {
    const query = new URLSearchParams();
    if (params.subcategory) query.set('subcategory', params.subcategory);
    if (params.source) query.set('source', params.source);
    if (params.district) query.set('district', params.district);
    if (params.venue) query.set('venue', params.venue);
    if (params.q) query.set('q', params.q);
    if (params.date_from) query.set('date_from', params.date_from);
    if (params.date_to) query.set('date_to', params.date_to);
    if (params.limit) query.set('limit', String(params.limit));
    if (params.offset) query.set('offset', String(params.offset));
    if (params.bbox && params.bbox.length === 4) {
      query.set('bbox', params.bbox.join(','));
    }

    const qs = query.toString() ? `?${query.toString()}` : '';
    const res = await fetch(`${API_BASE_URL}/api/v1/events${qs}`, {
      headers: { 'Accept': 'application/json' }
    });
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error('[Events] Failed to fetch events:', err);
    return null;
  }
}

/**
 * Fetch verified cultural venues, stadiums, and concert halls.
 * @returns {Promise<{total_venues: number, venues: VenueSummary[]}|null>}
 */
export async function fetchVenues() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/events/venues`);
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error('[Events] Failed to fetch venues:', err);
    return null;
  }
}

/**
 * Fetch Rotterdam municipal festivals and open cultural agendas.
 * @param {string} [district]
 * @returns {Promise<RotterdamEventFeatureCollection|null>}
 */
export async function fetchFestivals(district = null) {
  try {
    const q = district ? `?district=${encodeURIComponent(district)}` : '';
    const res = await fetch(`${API_BASE_URL}/api/v1/events/festivals${q}`);
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error('[Events] Failed to fetch festivals:', err);
    return null;
  }
}

/**
 * Fetch Rotterdam stadium fixtures (De Kuip, Het Kasteel, Woudestein).
 * @param {string} [club] - Filter by Feyenoord, Sparta, or Excelsior
 * @returns {Promise<RotterdamEventFeatureCollection|null>}
 */
export async function fetchStadiumFixtures(club = null) {
  try {
    const q = club ? `?club=${encodeURIComponent(club)}` : '';
    const res = await fetch(`${API_BASE_URL}/api/v1/events/stadiums${q}`);
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error('[Events] Failed to fetch stadium fixtures:', err);
    return null;
  }
}

/**
 * Fetch aggregated statistics of Rotterdam events.
 * @returns {Promise<EventStats|null>}
 */
export async function fetchEventStats() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/events/stats`);
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error('[Events] Failed to fetch event stats:', err);
    return null;
  }
}

/**
 * Fetch single event details by ID.
 * @param {string} eventId
 * @returns {Promise<RotterdamEventFeature|null>}
 */
export async function fetchEventById(eventId) {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/events/${encodeURIComponent(eventId)}`);
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error(`[Events] Failed to fetch event ${eventId}:`, err);
    return null;
  }
}

/**
 * Install dedicated Events MapLibre GL layer with pink/magenta branding.
 * @param {any} map
 * @param {Object} [options]
 */
export async function installEventsMapLayer(map, options = {}) {
  if (!map) return;

  const sourceId = 'rotterdam-events-dedicated';
  const glowLayerId = 'events-dedicated-glow';
  const coreLayerId = 'events-dedicated-core';

  const data = await fetchEvents({ limit: 300, ...options });

  if (map.getSource(sourceId)) {
    if (data) map.getSource(sourceId).setData(data);
    return;
  }

  map.addSource(sourceId, {
    type: 'geojson',
    data: data || { type: 'FeatureCollection', features: [] }
  });

  // Pink glowing outer halo
  map.addLayer({
    id: glowLayerId,
    type: 'circle',
    source: sourceId,
    paint: {
      'circle-radius': 14,
      'circle-color': '#ec4899',
      'circle-opacity': 0.35,
      'circle-blur': 0.5
    }
  });

  // Solid core circle
  map.addLayer({
    id: coreLayerId,
    type: 'circle',
    source: sourceId,
    paint: {
      'circle-radius': 7,
      'circle-color': '#ec4899',
      'circle-stroke-width': 2,
      'circle-stroke-color': '#ffffff',
      'circle-opacity': 0.95
    }
  });
}
