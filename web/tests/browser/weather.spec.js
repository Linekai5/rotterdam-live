import { test, expect } from '@playwright/test';
import { ROTTERDAM_WEATHER_NODES } from '../../src/lib/weatherEngine.js';

const weatherSnapshot = () => ({
  data_status: 'fresh', source: 'Open-Meteo / KNMI HARMONIE model',
  solar: { azimuth_deg: 202, elevation_deg: 23 },
  grid_nodes: ROTTERDAM_WEATHER_NODES.map(n => ({ ...n, timestamp: new Date().toISOString(),
    temperature_2m: 14.4, cloud_cover: 82, cloud_cover_low: 11, cloud_cover_mid: 12,
    cloud_cover_high: 77, precipitation: 0, wind_speed_10m: 17, wind_direction_10m: 240,
    wind_gusts_10m: 32, wind_u: 4, wind_v: 2, fog_density: 0, storm_intensity: 0 }))
});

const mockWeather = page => page.route('**/api/v1/weather/live', route => route.fulfill({ json: weatherSnapshot() }));

test('high cloud cover compiles and draws visible clouds without presets', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await mockWeather(page);
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

test('weather dashboard owns the Rotterdam clock and toggles between full and compact views', async ({ page }) => {
  const referenceTime = new Date();
  await page.clock.setFixedTime(referenceTime);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await mockWeather(page);
  await page.goto('/?weather=off');
  const panel = page.getByRole('complementary', { name: 'Rotterdam weather', exact: true });
  const toggle = panel.getByRole('button', { name: 'Rotterdam weather details' });
  const clock = panel.getByLabel('Current Rotterdam date and time');
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await expect(toggle).toContainText('82%');
  await expect(clock).toHaveAttribute('datetime', referenceTime.toISOString());
  await expect(clock).toContainText(new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: '2-digit', month: 'short', timeZone: 'Europe/Amsterdam' }).format(referenceTime));
  await expect(clock).toContainText(new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Amsterdam', timeZoneName: 'short' }).format(referenceTime));
  const expanded = await panel.boundingBox();
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(clock).toBeHidden();
  await expect(toggle).toContainText('14.4');
  const compact = await panel.boundingBox();
  expect(compact.width).toBeLessThan(expanded.width * 0.7);
  expect(compact.height).toBeLessThan(expanded.height * 0.5);
  await toggle.focus();
  await page.keyboard.press('Enter');
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await expect(clock).toBeVisible();
  await panel.getByText('Source & weather notes').click();
  await expect(panel.getByRole('button', { name: 'Refresh weather' })).toBeVisible();
});

test('mobile weather starts compact and can expand without horizontal overflow', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await mockWeather(page);
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 740 });
    await page.goto('/?weather=off');
    const panel = page.getByRole('complementary', { name: 'Rotterdam weather', exact: true });
    const toggle = panel.getByRole('button', { name: 'Rotterdam weather details' });
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await expect(toggle).toContainText('14.4');
    const compact = await panel.boundingBox();
    const brand = await page.locator('.identity').boundingBox();
    expect(compact.x).toBeGreaterThan(brand.x + brand.width);
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await expect(panel.getByLabel('Current Rotterdam date and time')).toBeVisible();
    const expanded = await panel.boundingBox();
    expect(expanded.width).toBeLessThanOrEqual(width - 30);
    expect(expanded.height).toBeGreaterThan(compact.height * 2);
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  }
});
