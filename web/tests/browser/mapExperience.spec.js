import { test, expect } from '@playwright/test';
import { openMap } from './navigation.js';

test('the opening view fits the current city, can pan, and permits a little more zoom-out', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await openMap(page, '/?weather=off');
  await page.waitForFunction(() => window.map?.isStyleLoaded());
  const initial = await page.evaluate(() => {
    const map = window.map;
    return { bounds: map.getBounds().toArray(), center: map.getCenter().lng, zoom: map.getZoom(), min: map.getMinZoom() };
  });
  expect(initial.bounds[0][0]).toBeLessThanOrEqual(4.379);
  expect(initial.bounds[0][1]).toBeLessThanOrEqual(51.861);
  expect(initial.bounds[1][0]).toBeGreaterThanOrEqual(4.602);
  expect(initial.bounds[1][1]).toBeGreaterThanOrEqual(51.995);
  expect(initial.zoom - initial.min).toBeGreaterThan(0.2);
  expect(initial.zoom - initial.min).toBeLessThan(0.5);
  await page.mouse.move(560, 490);
  await page.mouse.down();
  await page.mouse.move(790, 490, { steps: 10 });
  await page.mouse.up();
  await expect.poll(() => page.evaluate(center => Math.abs(window.map.getCenter().lng - center), initial.center)).toBeGreaterThan(0.005);
  await page.evaluate(() => window.map.zoomOut({ duration: 0 }));
  await expect.poll(() => page.evaluate(() => window.map.getZoom())).toBeLessThan(initial.zoom - 0.1);
  expect(await page.evaluate(() => window.map.getZoom() >= window.map.getMinZoom() - 0.00001)).toBe(true);
});

test('coincident news stays numbered at street zoom and every article can be opened', async ({ page }) => {
  const features = Array.from({ length: 71 }, (_, index) => ({
    type: 'Feature', id: `harbour-report-${index}`, geometry: { type: 'Point', coordinates: [4.48, 51.92] },
    properties: { title: `Harbour report ${index + 1}`, category: 'news', district: 'Rotterdam',
      details: { source: 'Regional source', link: `https://news.example/story-${index + 1}`, location_precision: 'city' } }
  }));
  await page.route('**/api/v1/live?**', route => route.fulfill({ json: { type: 'FeatureCollection', features } }));
  await openMap(page, '/?zoom=15&weather=off');
  await page.getByRole('button', { name: 'Local news', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Local news', exact: true })).toContainText('71 stories · 1 map location');
  await expect.poll(() => page.evaluate(() => {
    if (!window.map.getLayer('explore-news-cluster')) return 0;
    return window.map.queryRenderedFeatures({ layers: ['explore-news-cluster'] })[0]?.properties.point_count || 0;
  })).toBe(71);
  const point = await page.evaluate(() => { const p = window.map.project([4.48, 51.92]); return { x: p.x, y: p.y }; });
  await page.mouse.click(point.x, point.y);
  await expect(page.getByRole('heading', { name: 'Stories at this location' })).toBeVisible();
  await expect(page.getByText('Rotterdam-wide report', { exact: true }).first()).toBeVisible();
  await expect(page.locator('.result-row')).toHaveCount(40);
  await page.getByRole('button', { name: /Show more in this view/ }).click();
  await expect(page.locator('.result-row')).toHaveCount(71);
  await page.getByRole('button', { name: /Harbour report 71/ }).click();
  const details = page.getByRole('region', { name: 'Location details' });
  await expect(details.getByRole('heading', { name: 'Harbour report 71' })).toBeVisible();
  await expect(details.getByRole('link', { name: 'Read the original story' })).toHaveAttribute('href', 'https://news.example/story-71');
  await expect(details).toContainText('Rotterdam-wide report');
});

test('district outlines and selections stay beneath the city mask across map styles', async ({ page }) => {
  const district = { type: 'Feature', id: 'city-district', geometry: { type: 'Polygon', coordinates: [[[4.46, 51.90], [4.51, 51.90], [4.51, 51.94], [4.46, 51.94], [4.46, 51.90]]] }, properties: { name: 'City district' } };
  await page.route('**/api/v1/spatial/districts?**', route => route.fulfill({ json: { type: 'FeatureCollection', features: [district] } }));
  await openMap(page, '/?zoom=13&weather=off');
  await page.getByRole('button', { name: 'Neighbourhoods', exact: true }).click();
  await expect.poll(() => page.evaluate(() => !!window.map.getLayer('explore-districts-fill'))).toBe(true);
  await expect.poll(() => page.evaluate(() => window.map.queryRenderedFeatures({ layers: ['explore-districts-fill'] }).length)).toBeGreaterThan(0);
  const center = await page.evaluate(() => { const p = window.map.project([4.49, 51.92]); return { x: p.x, y: p.y }; });
  await page.mouse.click(center.x, center.y);
  await expect(page.getByRole('region', { name: 'Location details' })).toBeVisible();
  for (const mode of ['Aerial', 'Night', 'Atlas']) {
    if (mode !== 'Aerial') {
      await page.getByRole('button', { name: 'Map', exact: true }).click();
      await page.getByRole('button', { name: mode, exact: true }).click();
    }
    await expect.poll(() => page.evaluate(() => {
      const ids = window.map.getStyle().layers.map(layer => layer.id);
      const line = ids.indexOf('explore-districts-line');
      const selection = ids.indexOf('explorer-selection-area');
      const mask = ids.indexOf('rotterdam-water-mask');
      return line >= 0 && line < mask && selection >= 0 && selection < mask;
    })).toBe(true);
  }
});

test('successful HTTP preserves stale source warnings, provenance and provider totals', async ({ page }) => {
  await page.route('**/api/v1/events?**', route => route.fulfill({ json: {
    type: 'FeatureCollection', data_status: 'stale', source: 'Archive source', observed_at: '2001-01-01T00:00:00Z',
    coverage: { description: 'Partial city coverage' }, total_count: 71,
    features: [{ type: 'Feature', id: 'old-report', geometry: { type: 'Point', coordinates: [4.48, 51.92] }, properties: { title: 'Source report', timestamp: '2001-01-01T00:00:00Z' } }]
  } }));
  await openMap(page, '/?weather=off');
  const layer = page.getByRole('button', { name: 'What’s on', exact: true });
  await layer.click();
  await expect(layer).toContainText('Source data is outdated');
  await expect(page.getByText('Archive source', { exact: true })).toBeVisible();
  await expect(page.getByText('Partial city coverage', { exact: true })).toBeVisible();
  await expect(page.getByText('Provider reports 71 matches; 1 loaded.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: /In view/ }).click();
  await page.getByRole('button', { name: /Source report/ }).click();
  await expect(page.getByRole('region', { name: 'Location details' })).toContainText('Source data is outdated.');
});
