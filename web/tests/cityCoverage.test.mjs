import test from 'node:test';
import assert from 'node:assert/strict';
import { cityCoverage, featureForCityMap, pointIsInCity } from '../src/lib/cityCoverage.js';
import { calculateCameraLimits } from '../src/lib/cameraPhysics.js';

const feature = geometry => ({ type: 'Feature', id: 'coverage-fixture', geometry, properties: { title: 'Coverage example' } });

test('a navigation allowance does not make outside or masked-out points mappable', () => {
  const outside = [4.37, 51.92];
  const fence = calculateCameraLimits({ clientWidth: 1440, clientHeight: 960 }).navigationBounds;
  assert.ok(outside[0] > fence[0][0] && outside[0] < fence[1][0]);
  assert.equal(pointIsInCity(outside), false);
  assert.equal(cityCoverage(feature({ type: 'Point', coordinates: outside })), null);
  assert.equal(featureForCityMap(feature({ type: 'Point', coordinates: outside })), null);
  assert.equal(pointIsInCity([4.599, 51.90]), false, 'inside the tile rectangle still need not be inside the visible silhouette');
  assert.equal(pointIsInCity([4.48, 51.92]), true);
  assert.deepEqual(cityCoverage(feature({ type: 'Point', coordinates: [4.48, 51.92] })).bounds, [4.48, 51.92, 4.48, 51.92]);
});

test('a crossing road focuses its visible segment while mask rendering preserves its source geometry', () => {
  const road = feature({ type: 'LineString', coordinates: [[4.36, 51.92], [4.49, 51.92]] });
  const original = structuredClone(road);
  const coverage = cityCoverage(road);
  assert.ok(coverage.bounds[0] > 4.379 && coverage.bounds[0] < 4.49);
  assert.equal(coverage.bounds[2], 4.49);
  const mapped = featureForCityMap(road);
  assert.strictEqual(mapped, road);
  assert.equal(mapped.id, road.id);
  assert.deepEqual(mapped.properties, road.properties);
  assert.deepEqual(road, original, 'the provider record remains unchanged');
  assert.equal(cityCoverage(feature({ type: 'LineString', coordinates: [[4.61, 51.92], [4.63, 51.92]] })), null);
});

test('border polygons focus their city intersection but retain actual administrative outlines', () => {
  const area = feature({ type: 'Polygon', coordinates: [[[4.36, 51.90], [4.49, 51.90], [4.49, 51.94], [4.36, 51.94], [4.36, 51.90]]] });
  const coverage = cityCoverage(area);
  assert.ok(coverage.bounds[0] >= 4.379);
  assert.ok(coverage.bounds[2] <= 4.49);
  assert.strictEqual(featureForCityMap(area), area, 'do not draw an artificial outline at the clipped polygon edge');
  assert.equal(cityCoverage({ type: 'LineString', coordinates: [] }), null);
});
