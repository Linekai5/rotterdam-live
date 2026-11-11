import test from 'node:test';
import assert from 'node:assert/strict';
import { createWeatherEngineController, ROTTERDAM_WEATHER_NODES, interpolateWeatherAtPoint } from '../src/lib/weatherEngine.js';

test('live-only controller rejects old, invalid and stale snapshots; never invents initial weather', async () => {
  const originalFetch = globalThis.fetch;
  const originalInterval = globalThis.setInterval;
  globalThis.setInterval = () => null;
  let payload = { temperature: 14 };
  globalThis.fetch = async () => ({ ok: true, json: async () => payload });
  try {
    const controller = createWeatherEngineController(null);
    await controller.refreshLive();
    assert.equal(controller.getState().status, 'unavailable');
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
    assert.equal(controller.isEnabled(), false);
    payload = { data_status: 'fresh', grid_nodes: nodes.map(n => ({ ...n, timestamp: '2020-01-01T00:00:00Z' })), solar: { azimuth_deg: 180, elevation_deg: 30 } };
    await controller.refreshLive();
    assert.equal(controller.getState().status, 'stale');
    assert.equal(controller.isEnabled(), false);
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.setInterval = originalInterval;
  }
});
