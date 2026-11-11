import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';
import { ROTTERDAM_WEATHER_NODES } from '../src/lib/weatherEngine.js';

const execute = promisify(execFile);

test('release smoke check requests its selected origin and validates it with the real controller', async () => {
  const requests = [];
  const snapshot = {
    data_status: 'fresh', solar: { azimuth_deg: 180, elevation_deg: 30 },
    grid_nodes: ROTTERDAM_WEATHER_NODES.map(node => ({ ...node, timestamp: new Date().toISOString(),
      temperature_2m: 5, cloud_cover: 100, cloud_cover_low: 90, cloud_cover_mid: 80,
      cloud_cover_high: 60, precipitation: 0, wind_speed_10m: 10, wind_direction_10m: 90,
      wind_gusts_10m: 20, wind_u: -2.8, wind_v: 0, fog_density: 0, storm_intensity: 0 }))
  };
  const server = createServer((request, response) => {
    requests.push(request.url);
    response.setHeader('Content-Type', 'application/json');
    if (request.url === '/health/ready') response.end(JSON.stringify({ database: { connected: true }, redis: { connected: true } }));
    else if (request.url === '/api/v1/weather/live') response.end(JSON.stringify(snapshot));
    else { response.statusCode = 404; response.end('{}'); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const { stdout } = await execute(process.execPath,
      [fileURLToPath(new URL('../scripts/check-live-weather.mjs', import.meta.url)), `http://127.0.0.1:${server.address().port}`]);
    assert.deepEqual(requests, ['/health/ready', '/api/v1/weather/live']);
    assert.equal(JSON.parse(stdout).status, 'live');
    assert.equal(JSON.parse(stdout).nodes, 12);
  } finally { await new Promise(resolve => server.close(resolve)); }
});
