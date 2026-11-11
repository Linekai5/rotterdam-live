/** Verify the deployed API with the same controller used by the actual dashboard. */
import assert from 'node:assert/strict';
import { setTimeout as delay } from 'node:timers/promises';
import { createWeatherEngineController } from '../src/lib/weatherEngine.js';

const baseURL = new URL(process.argv[2] || 'https://rotterdamlive.nl');
const nativeFetch = globalThis.fetch;
const readiness = await nativeFetch(new URL('/health/ready', baseURL), { signal: AbortSignal.timeout(15000) });
assert.ok(readiness.ok, 'Backend readiness failed');
const dependencies = await readiness.json();
assert.equal(dependencies.database?.connected, true, 'Database is unavailable');
assert.equal(dependencies.redis?.connected, true, 'Redis is unavailable');

globalThis.fetch = (url, options) => {
  // Node's controller defaults to localhost; mirror the browser's serving origin.
  const requested = new URL(url, baseURL);
  return nativeFetch(new URL(requested.pathname + requested.search, baseURL), options);
};
// The smoke check needs one real fetch, without the UI's recurring poll timer.
const nativeInterval = globalThis.setInterval;
let controller;
try {
  globalThis.setInterval = () => null;
  controller = createWeatherEngineController(null);
  globalThis.setInterval = nativeInterval;
  const deadline = Date.now() + 18000;
  while (controller.getState().status === 'unavailable' && Date.now() < deadline) await delay(100);
  const state = controller.getState();
  assert.notEqual(state.status, 'unavailable', 'Weather API does not satisfy the dashboard contract');
  assert.equal(state.nodes.length, 12);
  assert.ok(Number.isFinite(state.temperatureC), 'No current model temperature');
  console.log(JSON.stringify({ status: state.status, temperatureC: state.temperatureC, validAt: state.validAt, nodes: state.nodes.length }));
} finally {
  globalThis.setInterval = nativeInterval;
  globalThis.fetch = nativeFetch;
}
