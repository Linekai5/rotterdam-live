import { languageLocale, translate } from './i18n.js';

// Display definitions follow the backend's actual filters and GeoJSON contracts.
export const MAP_DATASETS = [
  { id: 'events', label: 'What’s on', group: 'Discover', icon: 'spark', caption: 'Concerts, culture & city events', path: '/events', color: '#c6b8a2', source: 'Event listings', filters: [{ key: 'subcategory', label: 'Event type', options: [['', 'All events'], ['concert', 'Concerts'], ['festival', 'Festivals'], ['theatre', 'Theatre'], ['exhibition', 'Exhibitions'], ['stadium_fixture', 'Football']] }, { key: 'horizon', label: 'When', options: [['', 'Upcoming'], ['24h', 'Next 24 hours'], ['7d', 'Next 7 days']] }] },
  { id: 'districts', label: 'Neighbourhoods', group: 'Discover', icon: 'district', caption: 'District boundaries & local profiles', path: '/spatial/districts', geometry: 'area', citywide: true, color: '#b4bba6', source: 'CBS / municipal district data' },
  { id: 'retail', label: 'Shops & essentials', group: 'Discover', icon: 'shop', caption: 'Supermarkets & local shops', path: '/retail', color: '#b8aa98', source: 'OpenStreetMap directory', defaults: { shop_type: 'supermarket' }, filters: [{ key: 'shop_type', label: 'Place type', options: [['supermarket', 'Supermarkets'], ['convenience', 'Convenience stores'], ['bakery', 'Bakeries'], ['pharmacy', 'Pharmacies'], ['', 'All shops']] }] },
  { id: 'amenities', label: 'Useful places', group: 'Discover', icon: 'pin', caption: 'Water taps, public toilets & AEDs', path: '/amenities', color: '#acae99', source: 'Municipal amenities directory', defaults: { subcategory: 'water_tap' }, filters: [{ key: 'subcategory', label: 'Facility', options: [['water_tap', 'Drinking water'], ['toilet', 'Public toilets'], ['aed', 'AEDs'], ['ev_charger', 'EV chargers']] }] },
  { id: 'traffic', label: 'Traffic', group: 'Move', icon: 'route', caption: 'Corridor speeds & travel delays', path: '/mobility/traffic', geometry: 'line', color: '#b9a18a', source: 'Traffic corridor feed' },
  { id: 'parking', label: 'Parking', group: 'Move', icon: 'parking', caption: 'Parking locations & availability', path: '/mobility', query: { subcategory: 'parking' }, color: '#9facba', source: 'Parking availability feed' },
  { id: 'bridges', label: 'Bridges', group: 'Move', icon: 'bridge', caption: 'Current bridge information', path: '/mobility', query: { subcategory: 'bridge' }, color: '#b7b9aa', source: 'Bridge opening feed' },
  { id: 'cameras', label: 'Cameras', group: 'Live city', icon: 'camera', caption: 'Mapped camera locations & sources', path: '/amenities/cameras', color: '#b4bdb8', source: 'OpenStreetMap camera directory', defaults: { camera_type: '' }, filters: [{ key: 'camera_type', label: 'Camera type', options: [['', 'All mapped cameras'], ['traffic', 'Traffic cameras'], ['surveillance', 'Surveillance locations'], ['anpr', 'Speed cameras']] }] },
  { id: 'roadworks', label: 'Roadworks', group: 'Move', icon: 'works', caption: 'Road closures & planned works', path: '/mobility/roadworks', color: '#baa989', source: 'Municipal roadworks feed' },
  { id: 'crowd', label: 'City pulse', group: 'Live city', icon: 'pulse', caption: 'Estimated activity by district', path: '/crowd/live', geometry: 'area', citywide: true, color: '#a6b5a8', source: 'Rotterdam Live activity model' },
  { id: 'emergencies', label: 'Emergency reports', group: 'Live city', icon: 'report', caption: 'Recent regional dispatch reports', path: '/live', query: { category: 'emergency' }, color: '#ba9690', source: 'P2000 dispatch reports' },
  { id: 'news', label: 'Local news', group: 'Live city', icon: 'news', caption: 'Geolocated regional stories', path: '/live', query: { category: 'news' }, color: '#b6aaa0', source: 'Regional news feeds' },
  { id: 'environment', label: 'Air & environment', group: 'Live city', icon: 'leaf', caption: 'Air quality & environmental readings', path: '/environment', color: '#a6b5a8', source: 'Environmental feeds' }
];
export const DATASET_BY_ID = Object.fromEntries(MAP_DATASETS.map(item => [item.id, item]));
export const EMPTY_COLLECTION = { type: 'FeatureCollection', features: [] };

export function pointLocationKey(feature) {
  const coordinates = feature?.geometry?.type === 'Point' && feature.geometry.coordinates;
  return Array.isArray(coordinates) && coordinates.length >= 2 && coordinates.slice(0, 2).every(Number.isFinite) ? coordinates.slice(0, 2).map(value => value.toFixed(7)).join(',') : null;
}

export function locationPrecision(feature) {
  const p = feature?.properties || {};
  const value = p.location_precision || p.details?.location_precision;
  return ['exact', 'district', 'city', 'unknown'].includes(value) ? value : 'unknown';
}

export function locationLabel(feature, language = 'en') {
  const p = feature?.properties || {};
  const label = p.location_label || p.details?.location_label || p.district || p.district_name;
  const precision = locationPrecision(feature);
  if (precision === 'exact') return label || translate(language, 'Reported location');
  if (precision === 'district') return label ? translate(language, 'Approximate area: {area}', { area: label }) : translate(language, 'Approximate district location');
  if (precision === 'city') return translate(language, 'Rotterdam-wide report');
  return translate(language, 'Location is approximate');
}

/** Keep provider provenance separate from the time the browser received it. */
export function feedMetadata(collection, now = Date.now()) {
  const meta = collection.metadata || collection.meta || {};
  const rawStatus = String(collection.data_status ?? meta.data_status ?? 'unknown').toLowerCase();
  let freshness = ['fresh', 'stale', 'unavailable', 'unknown'].includes(rawStatus) ? rawStatus : ['error', 'failed'].includes(rawStatus) ? 'unavailable' : 'unknown';
  const observed = collection.observed_at || collection.source_updated_at || collection.measured_at || collection.timestamp || meta.observed_at || meta.source_updated_at;
  const observedAt = observed && Number.isFinite(Date.parse(observed)) ? observed : null;
  if (freshness === 'fresh' && (!observedAt || Date.parse(observedAt) > now + 5 * 60 * 1000)) freshness = 'unknown';
  const expires = collection.expires_at || meta.expires_at;
  const maxAge = collection.max_age_seconds ?? meta.max_age_seconds;
  if (freshness === 'fresh' && ((expires && Date.parse(expires) <= now) || (observedAt && Number.isFinite(maxAge) && maxAge > 0 && now - Date.parse(observedAt) > maxAge * 1000))) freshness = 'stale';
  const sourceValue = collection.source || meta.source;
  const source = typeof sourceValue === 'string' ? sourceValue : sourceValue?.name || null;
  const total = collection.total_count ?? meta.total_count;
  return { freshness, source, observedAt, coverage: collection.coverage ?? meta.coverage ?? null,
    providerTotal: Number.isInteger(total) && total >= 0 ? total : null };
}
const numberFormats = {
  en: new Intl.NumberFormat('en-GB', { maximumFractionDigits: 1 }),
  nl: new Intl.NumberFormat('nl-NL', { maximumFractionDigits: 1 })
};
export function formatNumber(value, language = 'en') {
  return Number.isFinite(value) ? numberFormats[language].format(value) : '—';
}
export function humanize(value, language = 'en') {
  if (typeof value !== 'string') return '';
  const label = value.replaceAll('_', ' ').replace(/^./, char => char.toUpperCase());
  const key = label.slice(0, 1) + label.slice(1).toLowerCase();
  const translated = translate(language, key);
  return translated === key ? label : translated;
}
export function formatDate(value, withTime = true, language = 'en') {
  const date = new Date(value);
  if (!value || !Number.isFinite(date.getTime())) return null;
  return new Intl.DateTimeFormat(languageLocale(language), {
    timeZone: 'Europe/Amsterdam', day: 'numeric', month: 'short',
    ...(withTime ? { hour: '2-digit', minute: '2-digit' } : {})
  }).format(date);
}
export function safeLink(value) {
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : null; } catch { return null; }
}
export function plainText(value) {
  return typeof value === 'string' ? value.replace(/<[^>]*>/g, ' ').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/\s+/g, ' ').trim() : '';
}
export function normalizeFeature(feature, datasetId = null, fetchedAt = Date.now()) {
  const properties = { ...feature.properties };
  for (const key of ['details', 'venue', 'price']) {
    if (typeof properties[key] === 'string') {
      try { properties[key] = JSON.parse(properties[key]); } catch { properties[key] = {}; }
    }
  }
  // MapLibre exposes geometry through a prototype getter; object spread alone
  // drops it and makes a visible marker appear to have no mappable location.
  const display = properties.display_geometry;
  const geometry = datasetId === 'traffic' && properties.geometry_quality === 'approximate_route_start' && display?.type === 'Point' && Array.isArray(display.coordinates) && display.coordinates.length >= 2 && display.coordinates.slice(0,2).every(Number.isFinite) ? display : feature.geometry;
  return { ...feature, type: 'Feature', geometry, properties: { ...properties, __dataset: datasetId || properties.__dataset || null, __fetchedAt: fetchedAt } };
}
// Ticket providers also return parking/upgrade products. They are not activities
// to discover on the city map; keep the original source links on actual events.
export function isPrimaryEvent(feature) {
  const p = feature.properties || {};
  const classifications = Array.isArray(p.details?.classifications) ? p.details.classifications : [];
  const transportation = classifications.some(item => /^(transportation|parking)$/i.test(item.type?.name || ''));
  return !transportation && !/^(parking (permit|ticket)|parkeerticket|parkeerkaart|locker ticket|vip upgrade)\b/i.test(p.title || '');
}
export function featureTitle(feature, language = 'en') {
  const p = feature?.properties || {};
  return p.details?.name || p.title || p.name || p.district_name || p.district || translate(language, 'Rotterdam location');
}
export function featureSubtitle(feature, language = 'en') {
  const p = feature?.properties || {};
  const tr = (message, variables) => translate(language, message, variables);
  if (p.__dataset === 'traffic') {
    return `${formatNumber(p.speed_kmh, language)} km/h · ${humanize(p.congestion_level, language) || tr('Corridor estimate')}`;
  }
  if (p.__dataset === 'crowd') return `${humanize(p.crowd_status, language)} · ${tr('estimated city activity')}`;
  if (p.__dataset === 'news') return locationLabel(feature, language);
  if (p.__dataset === 'cameras') {
    const type = p.details?.camera_type === 'anpr' ? tr('Speed camera') : humanize(p.details?.camera_type, language) || tr('Mapped camera');
    return `${type} · ${tr('mapped location')}`;
  }
  if (p.__dataset === 'parking' && Number.isFinite(p.details?.available_spaces)) {
    return tr('{count} spaces available', { count: formatNumber(p.details.available_spaces, language) });
  }
  return p.subtitle || p.venue?.name || p.venue_name || humanize(p.subcategory || p.shop_type || p.category, language)
    || tr(DATASET_BY_ID[p.__dataset]?.source || 'City information');
}
export function featureDetails(feature, language = 'en') {
  const p = feature?.properties || {};
  const d = p.details || {};
  const rows = [];
  const tr = (message, variables) => translate(language, message, variables);
  const number = value => formatNumber(value, language);
  const date = value => formatDate(value, true, language);
  const status = value => humanize(value, language);
  const add = (label, value) => {
    if (value !== null && value !== undefined && value !== '') rows.push({ label: tr(label), value: String(value) });
  };
  if (p.__dataset === 'traffic') {
    if (Number.isFinite(p.speed_kmh)) add('Speed', `${number(p.speed_kmh)} km/h`);
    if (Number.isFinite(p.delay_seconds)) add('Extra travel time', p.delay_seconds < 60 ? `${Math.round(p.delay_seconds)} sec` : `${number(p.delay_seconds / 60)} min`);
    if (Number.isFinite(p.current_travel_time_seconds)) add('Travel time', `${number(p.current_travel_time_seconds / 60)} min`);
    add('Conditions', status(p.congestion_level));
    if (p.speed_measurement_type === 'route_average_estimate') add('Measurement basis', tr('Calculated from reported journey time'));
    add('Measured', date(p.measured_at));
    if (p.geometry_quality === 'road_network_match') add('Map geometry', tr('Estimated path on the official road network'));
    if (p.geometry_quality === 'approximate_route_start') add('Map geometry', tr('Approximate route start; road path unverified'));
  }
  if (p.__dataset === 'crowd') {
    if (Number.isFinite(p.crowd_index)) add('Activity estimate', `${number(p.crowd_index)} / 100`);
    add('Activity', status(p.crowd_status));
    if (Number.isFinite(p.active_events_count)) add('Active events', number(p.active_events_count));
    if (Number.isFinite(p.parking_occupancy_avg_pct)) add('Monitored parking', tr('{count}% occupied', { count: number(p.parking_occupancy_avg_pct) }));
    if (Number.isFinite(d.monitored_garages_count)) add('Monitored garages', number(d.monitored_garages_count));
  }
  if (p.__dataset === 'events') {
    add('Starts', date(p.start_time));
    add('Ends', date(p.end_time));
    add('Venue', p.venue?.name || p.venue_name);
    if (p.price?.min != null) add('From', `${p.price.currency || 'EUR'} ${number(p.price.min)}`);
    add('Ticket status', status(p.status));
  }
  if (p.__dataset === 'news') {
    add('Map location', locationLabel(feature, language));
    add('Location source', p.location_source || d.location_source);
  }
  if (p.__dataset === 'parking') {
    add('Status', status(d.status));
    if (Number.isFinite(d.available_spaces)) add('Available', tr('{count} spaces', { count: number(d.available_spaces) }));
    if (Number.isFinite(d.total_capacity)) add('Capacity', tr('{count} spaces', { count: number(d.total_capacity) }));
    if (Number.isFinite(d.occupancy_rate)) add('Occupied', `${number(d.occupancy_rate)}%`);
    if (Number.isFinite(d.charging_points)) add('EV charging points', number(d.charging_points));
  }
  if (p.__dataset === 'bridges') {
    add('Road traffic', status(d.traffic_status));
    if (typeof d.active_opening === 'boolean') add('Opening for vessels', tr(d.active_opening ? 'Yes' : 'No'));
    add('Opening began', date(d.schedule?.start));
  }
  if (p.__dataset === 'cameras') {
    add('Camera type', d.camera_type === 'anpr' ? tr('Speed camera') : status(d.camera_type));
    add('Operator', d.operator);
    if (typeof d.has_live_feed === 'boolean') add('Public feed', tr(d.has_live_feed ? 'Listed by source' : 'No public feed listed'));
  }
  const address = [p.venue?.address || [p.street_name || d.street, p.house_number].filter(Boolean).join(' '), p.postal_code || p.venue?.postal_code].filter(Boolean).join(', ');
  add('Address', address); add('District', p.district || p.district_name);
  if (p.opening_hours || d.opening_hours) add('Opening hours', p.opening_hours || d.opening_hours);
  const accessible = d.wheelchair_status ?? d.wheelchair ?? d.wheelchair_accessible ?? p.wheelchair;
  if (accessible != null) {
    const access = accessible === false || accessible === 'no' ? tr('Not listed as accessible')
      : accessible === true || accessible === 'yes' ? tr('Listed as accessible') : status(String(accessible));
    add('Wheelchair access', access);
  }
  if (d.free_water === true) add('Drinking water', tr('Free public water tap'));
  if (Number.isFinite(d.temperature)) add('Temperature', `${number(d.temperature)}°C`);
  if (Number.isFinite(d.humidity)) add('Humidity', `${number(d.humidity)}%`);
  for (const [key, label] of [['pm25', 'PM2.5'], ['pm10', 'PM10'], ['no2', 'NO₂']]) {
    if (Number.isFinite(d[key])) add(label, `${number(d[key])} µg/m³`);
  }
  if (p.__dataset === 'roadworks') {
    add('Starts', date(d.start_date));
    add('Ends', date(d.end_date));
  }
  if (Number.isFinite(d.aqi)) add('Air quality index', number(d.aqi));
  const source = p.source ? humanize(p.source) : d.source || DATASET_BY_ID[p.__dataset]?.source;
  add('Source', source ? tr(source) : null);
  add(['retail', 'amenities', 'districts'].includes(p.__dataset) ? 'Record updated' : 'Reported', date(p.timestamp || p.updated_at));
  return rows;
}
export function featureDescription(feature, language = 'en') {
  const p = feature?.properties || {};
  if (p.__dataset === 'crowd') return translate(language, 'An estimated activity index combining available signals and a district model. It is not a live count of people.');
  return plainText(p.description || p.details?.summary || p.details?.description || p.details?.work_description || '');
}
export function featureAction(feature) {
  const p = feature?.properties || {};
  const cameraLink = p.__dataset === 'cameras' && p.details?.has_live_feed === true ? safeLink(p.details?.stream_url || p.details?.snapshot_url) : null;
  const mappedSource = p.__dataset === 'cameras' ? safeLink(p.details?.source_url) : null;
  const href = cameraLink || mappedSource || safeLink(p.ticket_url || p.details?.link || p.website || p.details?.website);
  return href ? { href, label: cameraLink ? 'Open public camera' : mappedSource ? 'View mapped source' : p.ticket_url ? 'Event information & tickets' : p.__dataset === 'news' ? 'Read the original story' : 'Visit source website' } : null;
}
export function geometryBounds(geometry) {
  if (!geometry || !Array.isArray(geometry.coordinates)) return null;
  let west = Infinity, south = Infinity, east = -Infinity, north = -Infinity;
  function visit(coordinates) {
    if (typeof coordinates?.[0] === 'number') {
      const [x, y] = coordinates;
      if (Number.isFinite(x) && Number.isFinite(y)) { west = Math.min(west, x); south = Math.min(south, y); east = Math.max(east, x); north = Math.max(north, y); }
    } else if (Array.isArray(coordinates)) coordinates.forEach(visit);
  }
  visit(geometry.coordinates);
  return Number.isFinite(west) ? [west, south, east, north] : null;
}
export function intersectsBounds(feature, bounds) {
  const box = geometryBounds(feature.geometry);
  return box && box[2] >= bounds[0] && box[0] <= bounds[2] && box[3] >= bounds[1] && box[1] <= bounds[3];
}
export function datasetParameters(definition, filters, bounds) {
  const params = new URLSearchParams({ limit: definition.id === 'roadworks' ? '500' : '150', ...definition.query });
  for (const filter of definition.filters || []) {
    const value = filters[filter.key];
    if (filter.key !== 'horizon' && filter.options.some(([key]) => key === value) && value) params.set(filter.key, value);
  }
  if (filters.horizon === '24h' || filters.horizon === '7d') {
    // Round to the hour to keep cache keys useful across small map movements.
    const start = Math.floor(Date.now() / 3600000) * 3600000;
    params.set('date_from', new Date(start).toISOString());
    params.set('date_to', new Date(start + (filters.horizon === '24h' ? 24 : 168) * 3600000).toISOString());
  }
  if (!definition.citywide) params.set('bbox', bounds.map(value => value.toFixed(4)).join(','));
  return params;
}
