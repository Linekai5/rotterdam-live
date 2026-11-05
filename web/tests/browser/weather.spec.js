import { test, expect } from '@playwright/test';
import { ROTTERDAM_WEATHER_NODES } from '../../src/lib/weatherEngine.js';

test('high cloud cover compiles and draws visible clouds without presets', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/v1/weather/live', route => route.fulfill({ json: {
    data_status: 'fresh', source: 'Open-Meteo / KNMI HARMONIE model',
    solar: { azimuth_deg: 202, elevation_deg: 23 },
    grid_nodes: ROTTERDAM_WEATHER_NODES.map(n => ({ ...n, timestamp: new Date().toISOString(),
      temperature_2m: 14.4, cloud_cover: 82, cloud_cover_low: 11, cloud_cover_mid: 12,
      cloud_cover_high: 77, precipitation: 0, wind_speed_10m: 17, wind_direction_10m: 240,
      wind_gusts_10m: 32, wind_u: 4, wind_v: 2, fog_density: 0, storm_intensity: 0 }))
  } }));
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Rotterdam weather details' })).toContainText('82%');
  expect(await page.evaluate(() => window.weatherController.getState().enabled)).toBe(true);
  await page.waitForFunction(() => {
    const layer = window.map?.getLayer('rotterdam-volumetric-weather')?.implementation;
    return layer?.program && layer.fbo && layer.lastFboRenderMs > 0;
  });
  const alpha = await page.evaluate(() => {
    const map = window.map;
    const layer = map.getLayer('rotterdam-volumetric-weather').implementation;
    const gl = map.painter.context.gl;
    const previous = gl.getParameter(gl.FRAMEBUFFER_BINDING);
    gl.bindFramebuffer(gl.FRAMEBUFFER, layer.fbo);
    const pixels = new Uint8Array(layer.fboWidth * layer.fboHeight * 4);
    gl.readPixels(0, 0, layer.fboWidth, layer.fboHeight, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
    gl.bindFramebuffer(gl.FRAMEBUFFER, previous);
    let visible = 0;
    let opacity = 0;
    let clear = 0;
    let dense = 0;
    for (let i = 3; i < pixels.length; i += 4) {
      if (pixels[i] > 25) visible++;
      opacity += pixels[i] / 255;
      if (pixels[i] < 15) clear++;
      if (pixels[i] > 100) dense++;
    }
    return { visible: visible / (pixels.length / 4), meanOpacity: opacity / (pixels.length / 4), clear: clear / (pixels.length / 4), dense: dense / (pixels.length / 4) };
  });
  expect(alpha.visible).toBeGreaterThan(0.2);
  // Cloud bodies and gaps must both exist; a uniform veil is a regression.
  expect(alpha.meanOpacity).toBeLessThan(0.75);
  expect(alpha.clear).toBeGreaterThan(0.01);
  expect(alpha.dense).toBeGreaterThan(0.01);
  await expect(page.getByText('SIM OVERRIDE')).toHaveCount(0);
  await page.getByRole('button', { name: 'Map', exact: true }).click();
  await expect(page.getByRole('switch', { name: 'Cloud atmosphere', exact: true })).toHaveAttribute('aria-checked', 'true');
  await page.getByRole('button', { name: 'Night', exact: true }).click();
  await page.getByRole('button', { name: 'Aerial', exact: true }).click();
  await page.waitForFunction(() => {
    const layer = window.map?.getLayer('rotterdam-volumetric-weather')?.implementation;
    return layer?.program && layer.lastFboRenderMs > 0;
  });
  expect(await page.evaluate(() => window.weatherController.isEnabled())).toBe(true);
  expect(errors).toEqual([]);
});
