import test from 'node:test';
import assert from 'node:assert/strict';
import { MAP_DATASETS, DATASET_BY_ID, normalizeFeature, featureDetails, featureAction, featureDescription, geometryBounds, intersectsBounds, datasetParameters, isPrimaryEvent } from '../src/lib/explorerData.js';
import { createMapDataController } from '../src/lib/mapDataController.js';

const point = (id = 'one', x = 4.48, y = 51.92) => ({ type: 'Feature', id, geometry: { type: 'Point', coordinates: [x, y] }, properties: { title: id } });
const response = features => ({ ok: true, json: async () => ({ type: 'FeatureCollection', features }) });
const settle = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
class FakeMap {
  constructor() { this.sources = new Map(); this.layers = new Map(); this.events = new Map(); }
  getBounds() { return { getWest: () => 4.4, getSouth: () => 51.88, getEast: () => 4.6, getNorth: () => 51.97 }; }
  getStyle() { return { layers: [...this.layers.values()] }; }
  getSource(id) { return this.sources.get(id); }
  addSource(id, value) { this.sources.set(id, { ...value, setData(data) { this.data = data; } }); }
  removeSource(id) { this.sources.delete(id); }
  getLayer(id) { return this.layers.get(id); }
  addLayer(layer) { this.layers.set(layer.id, layer); }
  removeLayer(id) { this.layers.delete(id); }
  setPaintProperty() {}
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
  const controller = createMapDataController(map, value => state = value, () => {});
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
  const controller = createMapDataController(map, value => state = value, () => {});
  try {
    controller.toggle('amenities');
    controller.setFilters('amenities', { subcategory: 'toilet' });
    assert.equal(pending[0].signal.aborted, true);
    pending[1].resolve(response([point('toilet')]));
    await settle();
    pending[0].resolve(response([point('water')]));
    await settle();
    assert.equal(state.amenities.features[0].id, 'toilet');
    assert.match(pending[1].url, /subcategory=toilet/);
    const requestCount = pending.length;
    map.layers.clear(); map.sources.clear(); map.fire('styledata');
    assert.equal(map.getSource('explore-amenities'), undefined, 'style listeners must not mutate an in-progress render');
    await settle();
    assert.equal(map.getSource('explore-amenities').data.features[0].id, 'toilet');
    assert.equal(pending.length, requestCount);
  } finally { controller.destroy(); globalThis.fetch = original; }
});
