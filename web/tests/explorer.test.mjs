import test from 'node:test';
import assert from 'node:assert/strict';
import { MAP_DATASETS, DATASET_BY_ID, normalizeFeature, featureSubtitle, featureDetails, featureAction, featureDescription, geometryBounds, intersectsBounds, datasetParameters, isPrimaryEvent, pointLocationKey, locationLabel, feedMetadata } from '../src/lib/explorerData.js';
import { createMapDataController, requestClusterData } from '../src/lib/mapDataController.js';
const createController = (map, onChange, onSelect, onHover) => createMapDataController(map, onChange, onSelect, onHover, { decodeSymbol: async () => ({ width: 1, height: 1, data: new Uint8Array(4) }) });

const point = (id = 'one', x = 4.48, y = 51.92) => ({ type: 'Feature', id, geometry: { type: 'Point', coordinates: [x, y] }, properties: { title: id } });
const response = features => ({ ok: true, json: async () => ({ type: 'FeatureCollection', features }) });
const settle = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };

test('point locations group honestly while area features and approximate news remain distinct', () => {
  assert.equal(pointLocationKey(point('one')), pointLocationKey(point('two')));
  assert.notEqual(pointLocationKey(point('one')), pointLocationKey(point('other', 4.49)));
  assert.equal(pointLocationKey({ geometry: { type: 'Polygon', coordinates: [[[4.4, 51.9], [4.5, 51.9], [4.4, 51.9]]] } }), null);
  assert.equal(pointLocationKey({}), null);
  const approximate = { ...point(), properties: { __dataset: 'news', details: { location_precision: 'city' } } };
  assert.equal(locationLabel(approximate), 'Rotterdam-wide report');
  assert.equal(featureSubtitle(approximate), 'Rotterdam-wide report');
  assert.equal(locationLabel(approximate, 'nl'), 'Bericht over heel Rotterdam');
  assert.equal(locationLabel({ ...point(), properties: { __dataset: 'news' } }), 'Location is approximate');
});

test('cluster requests support callbacks and Promises without duplicate delivery', async () => {
  for (const mode of ['callback', 'promise', 'both']) {
    const values = [];
    const source = { expand(id, callback) {
      if (mode !== 'promise') callback(null, id + 1);
      if (mode !== 'callback') return Promise.resolve(id + 1);
    } };
    requestClusterData(source, 'expand', [19], (error, value) => { assert.equal(error, null); values.push(value); });
    await settle();
    assert.deepEqual(values, [20], mode);
  }
});

test('source metadata never invents freshness from successful HTTP or empty collections', () => {
  assert.equal(feedMetadata({ features: [] }).freshness, 'unknown');
  assert.equal(feedMetadata({ data_status: 'fresh' }).freshness, 'unknown');
  assert.equal(feedMetadata({ data_status: 'stale', observed_at: '2001-01-01T00:00:00Z' }).freshness, 'stale');
  const now = Date.parse('2026-11-14T10:00:00Z');
  assert.equal(feedMetadata({ data_status: 'fresh', observed_at: '2026-11-14T09:00:00Z', max_age_seconds: 60 }, now).freshness, 'stale');
  assert.equal(feedMetadata({ data_status: 'fresh', observed_at: '2099-01-01T00:00:00Z' }, now).freshness, 'unknown');
});
class FakeMap {
  constructor() { this.sources = new Map(); this.layers = new Map(); this.images = new Map(); this.events = new Map(); }
  getBounds() { return { getWest: () => 4.4, getSouth: () => 51.88, getEast: () => 4.6, getNorth: () => 51.97 }; }
  getStyle() { return { layers: [...this.layers.values()] }; }
  getSource(id) { return this.sources.get(id); }
  addSource(id, value) { this.sources.set(id, { ...value, setData(data) { this.data = data; } }); }
  removeSource(id) { this.sources.delete(id); }
  getLayer(id) { return this.layers.get(id); }
  addLayer(layer) { this.layers.set(layer.id, layer); }
  removeLayer(id) { this.layers.delete(id); }
  setPaintProperty() {}
  setLayoutProperty(id, property, value) { this.layers.get(id).layout[property] = value; }
  hasImage(id) { return this.images.has(id); }
  addImage(id, data) { this.images.set(id, data); }
  removeImage(id) { this.images.delete(id); }
  on(event, handler) { if (!this.events.has(event)) this.events.set(event, new Set()); this.events.get(event).add(handler); }
  off(event, handler) { this.events.get(event)?.delete(handler); }
  fire(event, data = {}) { this.events.get(event)?.forEach(handler => handler(data)); }
}

test('provider records preserve zero/false metrics, parse map properties, and reject unsafe links', () => {
  const record = normalizeFeature({ ...point(), properties: { details: JSON.stringify({ available_spaces: 0, total_capacity: 100, occupancy_rate: 100, wheelchair_accessible: false }), ticket_url: 'javascript:alert(1)', description: '<p>Safe &amp; clear</p>' } }, 'parking');
  const rows = featureDetails(record);
  assert.equal(rows.find(r => r.label === 'Available').value, '0 spaces');
  assert.equal(rows.find(r => r.label === 'Wheelchair access').value, 'Not listed as accessible');
  assert.equal(isPrimaryEvent({ properties: { title: 'Parking permit European Commodities Exchange' } }), false);
  assert.equal(isPrimaryEvent({ properties: { title: 'An evening by the Maas' } }), true);
  assert.equal(featureAction(record), null);
  assert.equal(featureDescription(record), 'Safe & clear');
  assert.equal(featureAction({ properties: { website: 'https://example.com/info' } }).href, 'https://example.com/info');
  const mapHit = Object.create({ get geometry() { return { type: 'Point', coordinates: [4.48, 51.92] }; } });
  mapHit.properties = { title: 'Erasmusbrug', __dataset: 'bridges' };
  const selection = normalizeFeature(mapHit);
  assert.deepEqual(selection.geometry, { type: 'Point', coordinates: [4.48, 51.92] });
  assert.equal(intersectsBounds(selection, [4.4, 51.88, 4.6, 51.97]), true);
});
test('changing a facility filter updates its cluster glyph as well as its point records', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async url => {
    const subcategory = new URL(url, 'http://localhost').searchParams.get('subcategory');
    return response([{ ...point(subcategory), properties: { title: subcategory, subcategory } }]);
  };
  const map = new FakeMap();
  const controller = createController(map, () => {}, () => {});
  try {
    controller.toggle('amenities');
    await settle();
    assert.equal(map.getLayer('explore-amenities-cluster').layout['icon-image'], 'city-mark-cluster-water');
    controller.setFilters('amenities', { subcategory: 'toilet' });
    await settle();
    assert.equal(map.getLayer('explore-amenities-cluster').layout['icon-image'], 'city-mark-cluster-toilet');
    assert.equal(map.getSource('explore-amenities').data.features[0].properties.__marker, 'city-mark-toilet');
  } finally { controller.destroy(); globalThis.fetch = original; }
});
test('viewport and API parameters respect source scope and allowed filters', () => {
  assert.deepEqual(geometryBounds({ type: 'LineString', coordinates: [[4.4, 51.9], [4.5, 51.95]] }), [4.4, 51.9, 4.5, 51.95]);
  assert.equal(intersectsBounds(point('outside', 3.9), [4.4, 51.88, 4.6, 51.97]), false);
  const query = datasetParameters(DATASET_BY_ID.amenities, { subcategory: 'toilet', arbitrary: 'ignored' }, [4.4, 51.88, 4.6, 51.97]);
  assert.equal(query.get('subcategory'), 'toilet');
  assert.equal(query.get('arbitrary'), null);
  assert.equal(query.get('bbox'), '4.4000,51.8800,4.6000,51.9700');
  assert.equal(datasetParameters(DATASET_BY_ID.crowd, {}, [0,0,1,1]).has('bbox'), false);
  assert.equal(MAP_DATASETS.some(d => /supervisor/i.test(d.label)), false);
});
test('optional layers start idle, cap concurrent fetches, cancel on removal and ignore a late response', async () => {
  const original = globalThis.fetch;
  const pending = [];
  let active = 0, peak = 0;
  globalThis.fetch = (url, options) => new Promise(resolve => {
    active++; peak = Math.max(peak, active);
    pending.push({ url, signal: options.signal, resolve: result => { active--; resolve(result); } });
  });
  const map = new FakeMap();
  let state;
  const controller = createController(map, value => state = value, () => {});
  try {
    assert.equal(pending.length, 0);
    controller.toggle('events'); controller.toggle('parking'); controller.toggle('bridges');
    assert.equal(pending.length, 2);
    assert.equal(peak, 2);
    controller.toggle('events');
    assert.equal(pending[0].signal.aborted, true);
    pending[0].resolve(response([point('obsolete')]));
    await settle();
    assert.equal(pending.length, 3);
    assert.equal(state.events, undefined);
    assert.equal(map.getSource('explore-events'), undefined);
    pending[1].resolve(response([point('parking')])); pending[2].resolve(response([point('bridge')]));
    await settle();
    assert.equal(peak, 2);
    assert.equal(state.parking.status, 'ready');
    assert.equal(state.bridges.status, 'ready');
    assert.equal(state.parking.features[0].properties.__dataset, 'parking');
    controller.clear();
    assert.equal(Object.keys(state).length, 0);
    assert.equal(map.getSource('explore-parking'), undefined);
  } finally { controller.destroy(); globalThis.fetch = original; }
});
test('filter changes discard superseded results and style replacement restores selected data without fetching', async () => {
  const original = globalThis.fetch;
  const pending = [];
  globalThis.fetch = (url, options) => new Promise(resolve => pending.push({ url, signal: options.signal, resolve }));
  const map = new FakeMap(); let state;
  const controller = createController(map, value => state = value, () => {});
  try {
    controller.toggle('amenities');
    controller.setFilters('amenities', { subcategory: 'toilet' });
    assert.equal(pending[0].signal.aborted, true);
    pending[1].resolve(response([{ ...point('toilet'), properties: { title: 'toilet', subcategory: 'toilet' } }]));
    await settle();
    pending[0].resolve(response([{ ...point('water'), properties: { title: 'water', subcategory: 'water_tap' } }]));
    await settle();
    assert.equal(state.amenities.features[0].id, 'toilet');
    assert.match(pending[1].url, /subcategory=toilet/);
    const requestCount = pending.length;
    map.layers.clear(); map.sources.clear(); map.images.clear(); map.fire('styledata');
    assert.equal(map.getSource('explore-amenities'), undefined, 'style listeners must not mutate an in-progress render');
    await settle();
    assert.equal(map.getSource('explore-amenities').data.features[0].id, 'toilet');
    assert.equal(map.getLayer('explore-amenities-point').type, 'symbol');
    assert.equal(map.hasImage('city-mark-toilet'), true);
    assert.equal(pending.length, requestCount);
  } finally { controller.destroy(); globalThis.fetch = original; }
});

test('HTTP200 stale metadata survives normalization and unavailable refresh retains prior records', async () => {
  const original = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => ({ ok: true, json: async () => ++calls === 1
    ? { type: 'FeatureCollection', features: [point('last-report')], data_status: 'stale', source: 'Municipal source', observed_at: '2001-01-01T00:00:00Z', total_count: 71, coverage: { status: 'partial' } }
    : { type: 'FeatureCollection', features: [], data_status: 'unavailable', total_count: 0 } });
  const map = new FakeMap(); let state;
  const controller = createController(map, value => state = value, () => {});
  try {
    controller.toggle('events'); await settle();
    assert.equal(state.events.status, 'stale');
    assert.equal(state.events.freshness, 'stale');
    assert.equal(state.events.observedAt, '2001-01-01T00:00:00Z');
    assert.equal(state.events.source, 'Municipal source');
    assert.equal(state.events.providerTotal, 71);
    assert.equal(state.events.totalLoaded, 1);
    assert.equal(state.events.locations, 1);
    assert.equal(state.events.truncated, true);
    assert.deepEqual(state.events.coverage, { status: 'partial' });
    controller.retry('events'); await settle();
    assert.equal(calls, 2, 'manual retry must bypass the failed/stale cache');
    assert.equal(state.events.status, 'stale');
    assert.equal(state.events.features[0].id, 'last-report');
    assert.equal(state.events.providerTotal, null);
  } finally { controller.destroy(); globalThis.fetch = original; }
});

test('map coverage filters rendered pins while loaded records and provider totals remain truthful', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ type: 'FeatureCollection',
    features: [point('inside'), point('outside-silhouette', 4.599, 51.90)], total_count: 2 }) });
  const map = new FakeMap(); let state;
  const controller = createController(map, value => state = value, () => {});
  try {
    controller.toggle('news'); await settle();
    assert.equal(state.news.providerTotal, 2);
    assert.equal(state.news.totalLoaded, 2);
    assert.equal(state.news.features.length, 2);
    assert.equal(state.news.mappedLoaded, 1);
    assert.equal(state.news.mappedInView, 1);
    assert.equal(state.news.unmappedInView, 1);
    assert.equal(state.news.locations, 1);
    assert.deepEqual(map.getSource('explore-news').data.features.map(f => f.id), ['inside']);
    controller.select({ ...point('outside-search', 4.37, 51.92), properties: { title: 'Outside example' } });
    assert.equal(map.getSource('explorer-selection'), undefined);
  } finally { controller.destroy(); globalThis.fetch = original; }
});
