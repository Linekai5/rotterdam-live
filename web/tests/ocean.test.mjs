import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { PNG } from 'pngjs';
import { booleanPointInPolygon, point, area, intersect, featureCollection } from '@turf/turf';
import { boundaryRing, fieldBounds, oceanMesh, localPoint } from '../src/lib/oceanGeometry.js';

const read = path => readFileSync(new URL(path, import.meta.url));
const boundary = JSON.parse(read('../src/lib/rotterdam_boundary.json'));
const city = boundary.features?.[0] ?? boundary;
const ring = boundaryRing(boundary);
const metadata = JSON.parse(read('../src/lib/ocean-distance.json'));
const texture = PNG.sync.read(read('../src/lib/ocean-distance.png'));

function nearest(p) {
  return Math.sqrt(Math.min(...ring.map((a, i) => {
    const b = ring[(i + 1) % ring.length], dx = b[0] - a[0], dy = b[1] - a[1];
    const length = dx * dx + dy * dy;
    const t = length ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length)) : 0;
    return (p[0] - a[0] - t * dx) ** 2 + (p[1] - a[1] - t * dy) ** 2;
  })));
}

test('distance field matches the current boundary and exact segment distances', () => {
  assert.equal(metadata.boundaryHash, createHash('sha256').update(read('../src/lib/rotterdam_boundary.json')).digest('hex'));
  assert.deepEqual(metadata.bounds, fieldBounds(ring));
  const [x0,y0,x1,y1] = metadata.bounds;
  for (let y = 0; y < texture.height; y += 37) for (let x = 0; x < texture.width; x += 41) {
    const p = [x0 + (x + 0.5) / texture.width * (x1 - x0), y0 + (y + 0.5) / texture.height * (y1 - y0)];
    const offset = (y * texture.width + x) * 4;
    const actual = (texture.data[offset] * 256 + texture.data[offset + 1]) / 65535 * metadata.maxDistance;
    assert.ok(Math.abs(actual - Math.min(metadata.maxDistance, nearest(p))) < 0.025);
  }
  for (let i = 0; i < texture.width; i++) {
    for (const [x,y] of [[i,0],[i,texture.height-1],[0,i],[texture.width-1,i]]) {
      const offset = (y * texture.width + x) * 4;
      assert.equal(texture.data[offset] * 256 + texture.data[offset + 1], 65535, 'image edges must be pure deep ocean');
    }
  }
});

test('untiled ocean mesh leaves the city and northeast tip open', () => {
  const mesh = oceanMesh(ring);
  assert.ok(mesh.deviation < 1e-10);
  const contains = p => {
    for (let i = 0; i < mesh.indices.length; i += 3) {
      const points = Array.from(mesh.indices.slice(i, i + 3), j => [mesh.vertices[2*j],mesh.vertices[2*j+1]]);
      const signs = points.map((a,j) => {
        const b = points[(j+1)%3]; return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]);
      });
      if (signs.every(n=>n>=0) || signs.every(n=>n<=0)) return true;
    }
    return false;
  };
  for (let lat = 51.856; lat < 52.004; lat += 0.005) for (let lng = 4.37; lng < 4.615; lng += 0.006) {
    const p = localPoint([lng,lat]);
    if (nearest(p) < 1) continue;
    assert.equal(contains(p), !booleanPointInPolygon(point([lng,lat]), city), `mesh classification at ${lng}, ${lat}`);
  }
});

test('river blend stays inside both the city and surveyed water', () => {
  const blend = JSON.parse(read('../src/lib/river-blend.json'));
  const water = JSON.parse(read('../data/river-water.json'));
  for (const container of [city, water]) {
    const overlap = intersect(featureCollection([blend,container]));
    assert.ok(Math.abs(area(overlap)-area(blend)) < 0.1);
  }
});

test('elastic island boundary physics and responsive minZoom clamp', async () => {
  const {
    ROTTERDAM_ISLAND_SW,
    ROTTERDAM_ISLAND_NE,
    MAX_ZOOM_LIMIT,
    calculateResponsiveMinZoom,
    isPointInRotterdamIsland,
    clampToRotterdamIsland,
    cubicOutEasing
  } = await import('../src/lib/cameraPhysics.js');

  assert.deepEqual(ROTTERDAM_ISLAND_SW, [3.93, 51.83]);
  assert.deepEqual(ROTTERDAM_ISLAND_NE, [4.63, 52.01]);
  assert.equal(MAX_ZOOM_LIMIT, 19.5);

  // Responsive minZoom stays within [10.6, 11.2] across viewports
  for (const vp of [
    { clientWidth: 390, clientHeight: 844 },
    { clientWidth: 1440, clientHeight: 900 },
    { clientWidth: 2560, clientHeight: 1440 }
  ]) {
    const z = calculateResponsiveMinZoom(vp);
    assert.ok(z >= 10.6 && z <= 11.2, `minZoom ${z} out of [10.6, 11.2]`);
  }

  // Rotterdam Centrum [4.479, 51.922] and Maasvlakte [3.985, 51.958] are inside valid polygon
  assert.equal(isPointInRotterdamIsland(4.479, 51.922), true);
  assert.equal(isPointInRotterdamIsland(3.985, 51.958), true);

  // Drifting far outside into North Sea [3.75, 52.05] snaps back to nearest valid island frontier
  const snapped = clampToRotterdamIsland(3.75, 52.05);
  assert.equal(snapped.outside, true);
  assert.ok(snapped.distanceDeg > 0.1);
  assert.equal(isPointInRotterdamIsland(snapped.lng, snapped.lat), true);

  // Cubic-out easing curve properties
  assert.equal(cubicOutEasing(0), 0);
  assert.equal(cubicOutEasing(1), 1);
  assert.ok(cubicOutEasing(0.5) > 0.85);
});

test('12-node spatial weather interpolation, simulator presets, and altitude zoom-fade', async () => {
  const {
    ROTTERDAM_WEATHER_NODES,
    WEATHER_SIMULATOR_PRESETS,
    interpolateWeatherAtPoint,
    computeAltitudeCloudFade
  } = await import('../src/lib/weatherEngine.js');

  assert.equal(ROTTERDAM_WEATHER_NODES.length, 12);
  assert.equal(ROTTERDAM_WEATHER_NODES[0].name, 'Maasvlakte West');
  assert.equal(ROTTERDAM_WEATHER_NODES[6].name, 'Rotterdam Centrum');
  assert.equal(ROTTERDAM_WEATHER_NODES[11].name, 'Prins Alexander / Nesselande');

  // Verify Maasvlakte Coastal Squall preset exhibits strong coastal-to-inland precipitation gradient
  const squallNodes = WEATHER_SIMULATOR_PRESETS.coastal_squall.buildNodes();
  const westSample = interpolateWeatherAtPoint(3.985, 51.958, squallNodes);
  const eastSample = interpolateWeatherAtPoint(4.575, 51.965, squallNodes);
  assert.ok(westSample.precipitation > 4.0, 'Maasvlakte West must have heavy squall rain');
  assert.ok(eastSample.precipitation < 0.5, 'Nesselande East must remain mostly dry during coastal squall');
  assert.ok(westSample.storm_intensity > eastSample.storm_intensity);

  // Verify Phase 4 Altitude Zoom-Fade ("Dive Through the Clouds" mechanics)
  const macroView = computeAltitudeCloudFade(11.0, 0.5);
  const descentView = computeAltitudeCloudFade(13.1, 0.3);
  const streetView = computeAltitudeCloudFade(15.5, 0.2);

  assert.equal(macroView.phaseLabel, 'MACRO CANOPY');
  assert.ok(macroView.canopyOpacity >= 0.85, `Macro canopy opacity ${macroView.canopyOpacity} should be >= 0.85`);

  assert.equal(descentView.phaseLabel, 'CLOUD DESCENT');
  assert.ok(descentView.canopyOpacity < macroView.canopyOpacity && descentView.canopyOpacity > streetView.canopyOpacity);

  assert.equal(streetView.phaseLabel, 'STREET TACTICAL');
  assert.ok(streetView.canopyOpacity <= 0.04, `Street canopy opacity ${streetView.canopyOpacity} must be <= 0.04`);
  assert.ok(streetView.streetWetness > 0.9);
});

