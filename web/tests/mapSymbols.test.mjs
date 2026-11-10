import test from 'node:test';
import assert from 'node:assert/strict';
import { ICON_PATHS, markerKind, markerImageId, markerSvg, withMapSymbol, createMapSymbolRegistry } from '../src/lib/mapSymbols.js';

const settle = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
test('map categories resolve to distinct glyphs, including facility and event subtypes', () => {
  const expected = { concert: 'concert', festival: 'festival', theatre: 'theatre', exhibition: 'exhibition', stadium_fixture: 'football', water_tap: 'water', toilet: 'toilet', aed: 'aed', ev_charger: 'charging', camera: 'camera', bakery: 'bakery', pharmacy: 'pharmacy' };
  for (const [subcategory, kind] of Object.entries(expected)) {
    const feature = { type: 'Feature', properties: { __dataset: 'amenities', subcategory } };
    assert.equal(markerKind(feature), kind);
    assert.equal(withMapSymbol(feature).properties.__marker, markerImageId(kind));
    assert.ok(ICON_PATHS[kind]);
  }
  assert.equal(markerKind({ properties: { __dataset: 'bridges' } }), 'bridge');
  assert.equal(markerKind({ properties: { __dataset: 'cameras' } }), 'camera');
  assert.equal(markerKind({ properties: { __dataset: 'retail', subcategory: 'shop', shop_type: 'pharmacy' } }), 'pharmacy');
  assert.equal(markerKind({ properties: { __dataset: 'retail', shop_type: 'chemist' } }), 'pharmacy');
  assert.equal(markerKind({ properties: { __dataset: 'unknown', title: '<script>alert(1)</script>' } }), 'pin');
  assert.equal(new Set(['bridge', 'camera', 'parking', 'water', 'concert', 'toilet'].map(kind => ICON_PATHS[kind])).size, 6);
  assert.doesNotMatch(markerSvg('camera'), /<circle|https?:\/\/(?!www\.w3\.org)|<script/);
  assert.notEqual(markerSvg('event'), markerSvg('bridge'));
  assert.notEqual(markerSvg('cluster-event'), markerSvg('cluster-camera'));
  assert.notEqual(markerSvg('bridge'), markerSvg('bridge', true));
});

test('marker images decode once, restore after style replacement, and retain retina dimensions', async () => {
  const images = new Map(); let decodes = 0; let ready = 0;
  const image = { width: 80, height: 96, data: new Uint8Array(80 * 96 * 4) };
  const map = { hasImage: id => images.has(id), addImage: (id, data, options) => images.set(id, { data, options }), removeImage: id => images.delete(id) };
  const registry = createMapSymbolRegistry(map, () => ready++, async () => { decodes++; return image; });
  try {
    assert.equal(registry.ensure('camera'), false);
    assert.equal(registry.ensure('camera'), false);
    await settle();
    assert.equal(decodes, 1);
    assert.equal(ready, 1);
    assert.equal(registry.ensure('camera'), true);
    assert.equal(images.get(markerImageId('camera')).options.pixelRatio, 2);
    images.clear();
    assert.equal(registry.ensure('camera'), true);
    assert.equal(decodes, 1, 'style changes must reuse accepted pixels rather than decode again');
    assert.equal(images.get(markerImageId('camera')).data, image);
  } finally { registry.destroy(); }
  assert.equal(images.size, 0);
});

test('a late SVG decode cannot mutate a removed map or notify a disposed controller', async () => {
  let resolveImage; let mutations = 0; let ready = 0;
  const map = { hasImage: () => false, addImage: () => mutations++, removeImage: () => mutations++ };
  const registry = createMapSymbolRegistry(map, () => ready++, () => new Promise(resolve => resolveImage = resolve));
  registry.ensure('bridge');
  await settle();
  registry.destroy();
  resolveImage({ width: 1, height: 1, data: new Uint8Array(4) });
  await settle();
  assert.equal(mutations, 0);
  assert.equal(ready, 0);
  assert.equal(registry.ensure('bridge'), false);
});
