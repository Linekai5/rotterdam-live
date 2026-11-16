import { test, expect } from '@playwright/test';
import { openMap, dismissWelcome } from './navigation.js';
import { ROTTERDAM_WEATHER_NODES } from '../../src/lib/weatherEngine.js';
import { PNG } from 'pngjs';

const weatherSnapshot = () => ({
  data_status: 'fresh', source: 'Open-Meteo / KNMI HARMONIE model',
  solar: { azimuth_deg: 202, elevation_deg: 23 },
  grid_nodes: ROTTERDAM_WEATHER_NODES.map(n => ({ ...n, timestamp: new Date().toISOString(),
    temperature_2m: 14.4, cloud_cover: 82, cloud_cover_low: 11, cloud_cover_mid: 12,
    cloud_cover_high: 77, precipitation: 0, wind_speed_10m: 17, wind_direction_10m: 240,
    wind_gusts_10m: 32, wind_u: 4, wind_v: 2, fog_density: 0, storm_intensity: 0,
    weather_code: 45, weather_description: 'Mist' }))
});

const mockWeather = page => page.route('**/api/v1/weather/grid', route => route.fulfill({ json: weatherSnapshot() }));

test('current model clouds survive missing station observations and repeated reloads', async ({ page }) => {
  let modelStatus = 'fresh';
  let oldModel = false;
  let modelRequests = 0;
  let stationRequests = 0;
  const snapshot = () => ({ ...weatherSnapshot(), data_status: modelStatus,
    grid_nodes: weatherSnapshot().grid_nodes.map(n => ({ ...n, cloud_cover: 100,
      cloud_cover_low: 100, cloud_cover_mid: 100, cloud_cover_high: 0,
      timestamp: new Date(Date.now() - (oldModel ? 31 * 60000 : 0)).toISOString() })) });
  await page.route('**/api/v1/weather/live', route => {
    stationRequests++;
    return route.fulfill({ json: { ...snapshot(), data_status: 'stale', station_status: 'unavailable', model_status: 'fresh' } });
  });
  await page.route('**/api/v1/weather/grid', route => {
    modelRequests++;
    return route.fulfill({ json: snapshot() });
  });
  for (let attempt = 0; attempt < 3; attempt++) {
    await openMap(page, '/');
    const dashboard = page.getByRole('button', { name: 'Rotterdam weather details' });
    await expect(dashboard).toContainText('100%');
    await expect(dashboard).toContainText('Live');
    await page.waitForFunction(() => window.weatherController?.isEnabled() &&
      map.getLayer('rotterdam-volumetric-weather')?.implementation.lastFboRenderMs > 0);
    const coverage = await page.evaluate(() => {
      const layer = map.getLayer('rotterdam-volumetric-weather').implementation;
      const gl = map.painter.context.gl;
      const previous = gl.getParameter(gl.FRAMEBUFFER_BINDING);
      gl.bindFramebuffer(gl.FRAMEBUFFER, layer.fbo);
      const pixels = new Uint8Array(layer.fboWidth * layer.fboHeight * 4);
      gl.readPixels(0, 0, layer.fboWidth, layer.fboHeight, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
      gl.bindFramebuffer(gl.FRAMEBUFFER, previous);
      let visible = 0;
      for (let i = 3; i < pixels.length; i += 4) if (pixels[i] > 25) visible++;
      return visible / (pixels.length / 4);
    });
    expect(coverage).toBeGreaterThan(0.2);
  }
  modelStatus = 'stale';
  await page.evaluate(() => weatherController.refreshLive());
  expect(await page.evaluate(() => weatherController.isEnabled())).toBe(true);
  await expect(page.getByRole('button', { name: 'Rotterdam weather details' })).toContainText('Refresh delayed');
  await page.getByText('Source & weather notes').click();
  await expect(page.getByText('Weather refresh is delayed. Showing the latest model while it remains current.', { exact: true })).toBeVisible();
  modelStatus = 'fresh'; oldModel = true;
  await page.evaluate(() => weatherController.refreshLive());
  expect(await page.evaluate(() => weatherController.isEnabled())).toBe(false);
  await expect(page.getByRole('button', { name: 'Rotterdam weather details' })).toContainText('Outdated');
  oldModel = false;
  await page.evaluate(() => weatherController.refreshLive());
  expect(await page.evaluate(() => weatherController.isEnabled())).toBe(true);
  expect(stationRequests).toBe(0);
  expect(modelRequests).toBeGreaterThanOrEqual(6);
});

test('clouds keep covering the water after data layers, selections and style changes', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await mockWeather(page);
  await page.route('**/api/v1/spatial/districts?**', route => route.fulfill({ json: {
    type: 'FeatureCollection', features: [{ type: 'Feature', id: 'cloud-test-district',
      geometry: { type: 'Polygon', coordinates: [[[4.46, 51.90], [4.51, 51.90], [4.51, 51.94], [4.46, 51.94], [4.46, 51.90]]] },
      properties: { name: 'Cloud test district' } }]
  } }));
  await page.route('**/api/v1/live?**', route => route.fulfill({ json: {
    type: 'FeatureCollection', features: [{ type: 'Feature', id: 'cloud-test-news',
      geometry: { type: 'Point', coordinates: [4.48, 51.92] },
      properties: { title: 'City cloud-order report', category: 'news' } }]
  } }));
  await openMap(page, '/');
  await page.waitForFunction(() => window.map?.getLayer('coastal-ocean') &&
    window.map?.getLayer('rotterdam-volumetric-weather')?.implementation.lastFboRenderMs > 0);
  const camera = await page.evaluate(() => ({ center: map.getCenter().toArray(), zoom: map.getZoom() }));
  async function waterPixels() {
    await page.evaluate(() => new Promise(resolve => { map.once('render', resolve); map.triggerRepaint(); }));
    return PNG.sync.read(await page.screenshot({ clip: { x: 1100, y: 360, width: 80, height: 300 } })).data;
  }
  function difference(a, b) {
    let total = 0;
    for (let i = 0; i < a.length; i++) if (i % 4 !== 3) total += Math.abs(a[i] - b[i]);
    return total / (a.length / 4 * 3);
  }
  async function expectAtmosphereOrder() {
    await expect.poll(() => page.evaluate(() => {
      // Serialized style JSON omits custom layers. Use the actual render order.
      const order = map.getLayersOrder();
      const weather = order.indexOf('rotterdam-volumetric-weather');
      const ground = ['rotterdam-water-mask', 'coastal-river-blend', 'coastal-ocean'];
      const markers = order.filter(id => (id.startsWith('explore-') || id.startsWith('explorer-selection')) && map.getLayer(id).type === 'symbol');
      return { aboveWater: weather >= 0 && ground.every(id => order.indexOf(id) >= 0 && order.indexOf(id) < weather),
        belowMarkers: markers.every(id => order.indexOf(id) > weather) };
    })).toEqual({ aboveWater: true, belowMarkers: true });
  }
  const cloudyWater = await waterPixels();
  await page.evaluate(() => weatherController.setEnabled(false));
  const clearWater = await waterPixels();
  expect(difference(cloudyWater, clearWater)).toBeGreaterThan(5);
  await page.evaluate(() => weatherController.setEnabled(true));
  await expectAtmosphereOrder();

  await page.getByRole('button', { name: 'Neighbourhoods', exact: true }).click();
  await page.waitForFunction(() => map.getLayer('explore-districts-line'));
  await expectAtmosphereOrder();
  expect(difference(await waterPixels(), cloudyWater)).toBeLessThan(2);
  await page.getByRole('button', { name: 'Local news', exact: true }).click();
  await page.waitForFunction(() => map.getLayer('explore-news-point'));
  await expectAtmosphereOrder();
  await page.getByRole('button', { name: /In view/ }).click();
  await page.getByRole('button', { name: /City cloud-order report/ }).click();
  await page.waitForFunction(() => map.getLayer('explorer-selection-point'));
  await expectAtmosphereOrder();
  await page.evaluate(camera => map.jumpTo(camera), camera);
  expect(difference(await waterPixels(), cloudyWater)).toBeLessThan(2);

  await page.getByRole('button', { name: 'Map', exact: true }).click();
  for (const mode of ['Night', 'Aerial', 'Atlas', 'Aerial']) {
    await page.getByRole('button', { name: mode, exact: true }).click();
    if (mode === 'Aerial') {
      await expectAtmosphereOrder();
      expect(difference(await waterPixels(), cloudyWater)).toBeLessThan(2);
    } else await expect.poll(() => page.evaluate(() => !!map.getLayer('rotterdam-volumetric-weather'))).toBe(false);
  }
  await page.evaluate(() => new Promise(resolve => {
    map.once('webglcontextrestored', resolve);
    const extension = map.painter.context.gl.getExtension('WEBGL_lose_context');
    extension.loseContext();
    setTimeout(() => extension.restoreContext(), 100);
  }));
  await expectAtmosphereOrder();
  expect(difference(await waterPixels(), cloudyWater)).toBeLessThan(2);
  await page.setViewportSize({ width: 1440, height: 960 });
  await expectAtmosphereOrder();
  expect(await page.evaluate(() => map.painter.context.gl.getError())).toBe(0);
  expect(errors).toEqual([]);
});

test('model clouds render on Aerial and clear when switching to Night or Atlas', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await mockWeather(page);
  await openMap(page, '/');
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
  const cloudSwitch = page.getByRole('switch', { name: 'Cloud atmosphere', exact: true });
  for (const mode of ['Night', 'Atlas']) {
    await page.getByRole('button', { name: mode, exact: true }).click();
    await expect(cloudSwitch).toBeDisabled();
    await expect.poll(() => page.evaluate(() => ({
      aerial: !!window.map.getSource('satellite'),
      atmosphere: !!window.map.getLayer('rotterdam-volumetric-weather'),
      weatherStatus: window.weatherController.getState().status
    }))).toEqual({ aerial: false, atmosphere: false, weatherStatus: 'live' });
  }
  await page.getByRole('button', { name: 'Aerial', exact: true }).click();
  await expect(cloudSwitch).toBeEnabled();
  await expect(cloudSwitch).toHaveAttribute('aria-checked', 'true');
  await page.waitForFunction(() => {
    const layer = window.map?.getLayer('rotterdam-volumetric-weather')?.implementation;
    return layer?.program && layer.lastFboRenderMs > 0;
  });
  expect(await page.evaluate(() => window.weatherController.isEnabled())).toBe(true);
  expect(errors).toEqual([]);
});

test('NL/EN switches the interface and weather in place, saves the choice, and fits mobile', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await mockWeather(page);
  const requests = [];
  await page.route('**/api/v1/events?**', route => {
    requests.push(new URL(route.request().url()).searchParams.get('subcategory'));
    return route.fulfill({ json: { type: 'FeatureCollection', features: [{
      type: 'Feature', id: 'maas-concert', geometry: { type: 'Point', coordinates: [4.48, 51.92] },
      properties: { title: 'Concert aan de Maas', subcategory: 'concert', start_time: '2027-01-06T20:00:00+01:00' }
    }] } });
  });
  await openMap(page, '/?weather=off');
  const html = page.locator('html');
  await expect(html).toHaveAttribute('lang', 'en');
  await expect(page.getByRole('button', { name: 'Rotterdam weather details' })).toContainText('Fog');
  await page.getByRole('button', { name: 'What’s on', exact: true }).click();
  await page.getByLabel('What’s on: Event type').selectOption('concert');
  await expect.poll(() => requests.at(-1)).toBe('concert');
  await expect(page.getByRole('button', { name: 'What’s on', exact: true })).toContainText('1 in this view');

  const beforeLanguageChange = requests.length;
  await page.getByRole('button', { name: 'Nederlands', exact: true }).click();
  await expect(html).toHaveAttribute('lang', 'nl');
  await expect(page.getByRole('heading', { name: 'Verken Rotterdam.' })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Zoek in Rotterdam' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Weerdetails Rotterdam' })).toContainText('Mist');
  await expect(page.getByRole('button', { name: 'Weerdetails Rotterdam' })).toContainText('14,4');
  await expect(page.getByLabel('Uitagenda: Type evenement')).toHaveValue('concert');
  expect(requests.length).toBe(beforeLanguageChange);
  await page.getByRole('button', { name: /In beeld/ }).click();
  await page.getByRole('button', { name: /Concert aan de Maas/ }).click();
  const details = page.getByRole('region', { name: 'Locatiegegevens' });
  await expect(details.getByRole('heading', { name: 'Concert aan de Maas' })).toBeVisible();
  await expect(details).toContainText('Datum en tijd');

  await page.reload();
  await dismissWelcome(page);
  await expect(html).toHaveAttribute('lang', 'nl');
  await page.getByRole('button', { name: 'Kaart', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Luchtfoto', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Nacht', exact: true })).toBeVisible();
  await page.setViewportSize({ width: 320, height: 740 });
  const explorer = page.getByRole('button', { name: /Ontdek de stad/ });
  const languages = page.getByRole('group', { name: 'Taal' });
  await expect(explorer).toBeVisible();
  const explorerBox = await explorer.boundingBox();
  const languageBox = await languages.boundingBox();
  expect(languageBox.x).toBeGreaterThan(explorerBox.x + explorerBox.width);
  expect(languageBox.x + languageBox.width).toBeLessThan(320);
  await page.getByRole('button', { name: 'English', exact: true }).click();
  await expect(html).toHaveAttribute('lang', 'en');
  await expect(page.getByRole('button', { name: /Explore the city/ })).toBeVisible();
});

test('weather dashboard owns the Rotterdam clock and toggles between full and compact views', async ({ page }) => {
  const referenceTime = new Date();
  await page.clock.setFixedTime(referenceTime);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await mockWeather(page);
  await openMap(page, '/?weather=off');
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
    await openMap(page, '/?weather=off');
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
