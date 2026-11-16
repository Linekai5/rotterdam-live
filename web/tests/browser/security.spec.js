import { test, expect } from '@playwright/test';
import { openMap } from './navigation.js';

test('untrusted feature text cannot execute HTML or create a script link', async ({ page }) => {
  const title = '<img src="invalid-security-probe" onerror="window.__featureProbe=true">';
  await page.route('**/api/v1/events?**', route => route.fulfill({ json: {
    type: 'FeatureCollection', features: [{
      type: 'Feature', id: 'untrusted-feature', geometry: { type: 'Point', coordinates: [4.48, 51.92] },
      properties: { title, subcategory: 'concert', source_url: 'javascript:window.__featureProbe=true',
        description: '<script>window.__featureProbe=true</script>Provider description' }
    }]
  } }));
  await openMap(page, '/?weather=off');
  await page.getByRole('button', { name: 'What’s on', exact: true }).click();
  await page.getByRole('button', { name: /In view/ }).click();
  await page.getByRole('button').filter({ hasText: title }).click();
  const details = page.getByRole('region', { name: 'Location details' });
  await expect(details.getByRole('heading')).toHaveText(title);
  await expect(details.locator('img, script, a[href^="javascript:"]')).toHaveCount(0);
  expect(await page.evaluate(() => !!window.__featureProbe)).toBe(false);
});

test('MapLibre sanitizes adjacent dangerous attribution attributes', async ({ page }) => {
  await openMap(page, '/?weather=off');
  await page.waitForFunction(() => window.map?.isStyleLoaded());
  await page.evaluate(async () => {
    const { AttributionControl } = await import('/node_modules/maplibre-gl/dist/maplibre-gl.mjs');
    window.__attributionProbe = false;
    window.map.addControl(new AttributionControl({ compact: false,
      customAttribution: '<details open onload="window.__attributionProbe=true" ontoggle="window.__attributionProbe=true">Provider credit</details>'
    }), 'bottom-left');
  });
  const attribution = page.locator('.maplibregl-ctrl-attrib-inner');
  // MapLibre's allow list drops unsupported elements with their whole subtree.
  await expect(attribution.locator('details')).toHaveCount(0);
  await expect(attribution).not.toContainText('Provider credit');
  await expect(attribution.locator('[onload], [ontoggle]')).toHaveCount(0);
  expect(await page.evaluate(() => window.__attributionProbe)).toBe(false);
});

test('a device without WebGL2 receives an accessible map error and recovery control', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type, ...args) {
      return type === 'webgl2' ? null : original.call(this, type, ...args);
    };
  });
  await openMap(page, '/?weather=off');
  const alert = page.getByRole('alert');
  await expect(alert.getByRole('heading', { name: 'The map couldn’t start.' })).toBeVisible();
  await expect(alert.getByRole('button', { name: 'Reload map' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
});
