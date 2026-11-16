import test from 'node:test';
import assert from 'node:assert/strict';
import { createWeatherEngineController, ROTTERDAM_WEATHER_NODES, interpolateWeatherAtPoint } from '../src/lib/weatherEngine.js';

test('clouds use the model grid independently of missing station observations', async () => {
  const originalFetch = globalThis.fetch;
  const originalInterval = globalThis.setInterval;
  const requests = [];
  const base = { data_status: 'fresh', solar: { azimuth_deg: 180, elevation_deg: 30 },
    grid_nodes: ROTTERDAM_WEATHER_NODES.map(n => ({ ...n, timestamp: new Date().toISOString(), temperature_2m: 14,
      cloud_cover: 100, cloud_cover_low: 100, cloud_cover_mid: 100, cloud_cover_high: 0, precipitation: 0,
      wind_speed_10m: 0, wind_direction_10m: 0, wind_gusts_10m: 0, wind_u: 0, wind_v: 0, fog_density: 0, storm_intensity: 0 })) };
  let payload = base;
  globalThis.setInterval = () => null;
  globalThis.fetch = async url => {
    requests.push(url);
    return { ok: true, json: async () => url.endsWith('/weather/grid') ? payload
      : { ...base, data_status: 'stale', station_status: 'unavailable', model_status: 'fresh' } };
  };
  try {
    const controller = createWeatherEngineController(null);
    await new Promise(resolve => setImmediate(resolve));
    for (const [overrides, visible] of [
      [{}, true],
      [{ data_status: 'stale' }, true],
      [{ grid_nodes: base.grid_nodes.map((n, i) => i ? n : { ...n, timestamp: new Date(Date.now() - 31 * 60000).toISOString() }) }, false],
      [{}, true],
    ]) {
      payload = { ...base, ...overrides };
      await controller.refreshLive();
      assert.equal(controller.isEnabled(), visible);
      assert.equal(controller.getState().status, visible && payload.data_status === 'fresh' ? 'live' : 'stale');
      assert.equal(controller.getState().refreshDelayed, visible && payload.data_status === 'stale');
      assert.equal(controller.getState().cloudCoverPct, 100);
    }
    assert.ok(requests.length > 0);
    assert.ok(requests.every(url => url.endsWith('/weather/grid')), 'Cloud rendering must not depend on the combined station feed');
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.setInterval = originalInterval;
  }
});

test('controller rejects invalid snapshots, retains current model data through refresh delays and never invents weather', async () => {
  const originalFetch = globalThis.fetch;
  const originalInterval = globalThis.setInterval;
  globalThis.setInterval = () => null;
  let payload = { temperature: 14 };
  globalThis.fetch = async () => ({ ok: true, json: async () => payload });
  try {
    const controller = createWeatherEngineController(null);
    await controller.refreshLive();
    assert.equal(controller.getState().status, 'unavailable');
    assert.equal(controller.isEnabled(), false);
    assert.deepEqual(controller.getState().nodes, []);
    assert.equal(controller.setPreset, undefined);
    assert.equal(interpolateWeatherAtPoint(4.48, 51.92), null);
    const nodes = ROTTERDAM_WEATHER_NODES.map(n => ({ ...n, timestamp: new Date().toISOString(), temperature_2m: 14,
      cloud_cover: 20, cloud_cover_low: 20, cloud_cover_mid: 0, cloud_cover_high: 0, precipitation: 0,
      wind_speed_10m: 0, wind_direction_10m: 0, wind_gusts_10m: 0, wind_u: 0, wind_v: 0, fog_density: 0, storm_intensity: 0 }));
    payload = { data_status: 'fresh', grid_nodes: nodes, solar: { azimuth_deg: 180, elevation_deg: 30 } };
    await controller.refreshLive();
    assert.equal(controller.getState().status, 'live');
    assert.equal(controller.isEnabled(), true);
    assert.equal(controller.getState().windSpeedKmh, 0);
    payload = { temperature: 20 };
    await controller.refreshLive();
    assert.equal(controller.getState().status, 'stale');
    assert.equal(controller.getState().temperatureC, 14);
    assert.equal(controller.getState().refreshDelayed, true);
    assert.equal(controller.isEnabled(), true);
    const originalNow = Date.now;
    try {
      Date.now = () => originalNow() + 31 * 60000;
      assert.equal(controller.isEnabled(), false, 'Retained model must expire even without another response');
      assert.equal(controller.getState().refreshDelayed, false);
    } finally { Date.now = originalNow; }
    payload = { data_status: 'fresh', grid_nodes: nodes.map(n => ({ ...n, timestamp: '2020-01-01T00:00:00Z' })), solar: { azimuth_deg: 180, elevation_deg: 30 } };
    await controller.refreshLive();
    assert.equal(controller.getState().status, 'stale');
    assert.equal(controller.isEnabled(), false);
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.setInterval = originalInterval;
  }
});
