import { test, expect } from '@playwright/test';
import { openMap } from './navigation.js';

const inside = { type: 'Feature', id: 'inside-record', geometry: { type: 'Point', coordinates: [4.48, 51.92] }, properties: { title: 'Inner map example' } };
const outside = { type: 'Feature', id: 'outside-record', geometry: { type: 'Point', coordinates: [4.37, 51.92] }, properties: { title: 'Outside map example' } };

test('outside-area search records remain readable without a misleading camera flight or pin', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.route('**/api/v1/search?**', route => route.fulfill({ json: { type: 'FeatureCollection', features: [outside, inside] } }));
  await openMap(page, '/?weather=off');
  await page.waitForFunction(() => window.map?.isStyleLoaded());
  const before = await page.evaluate(() => ({ center: window.map.getCenter().toArray(), zoom: window.map.getZoom() }));
  await page.getByRole('textbox', { name: 'Search Rotterdam' }).fill('Coverage');
  const row = page.getByRole('button', { name: /Outside map example/ });
  await expect(row).toContainText('Outside current map area');
  await row.click();
  const details = page.getByRole('region', { name: 'Location details' });
  await expect(details.getByRole('heading', { name: 'Outside map example' })).toBeVisible();
  await expect(details).toContainText('This place is outside the central map area.');
  await expect(details.getByRole('button', { name: 'Show on map' })).toHaveCount(0);
  expect(await page.evaluate(() => ({ center: window.map.getCenter().toArray(), zoom: window.map.getZoom() }))).toEqual(before);
  expect(await page.evaluate(async () => {
    const source = window.map.getSource('explorer-selection');
    return source ? (await source.getData()).features.length : 0;
  })).toBe(0);
  await page.getByRole('button', { name: 'Close location details' }).click();
  await page.getByRole('textbox', { name: 'Search Rotterdam' }).fill('Coverage');
  await page.getByRole('button', { name: /Inner map example/ }).click();
  await expect(details.getByRole('button', { name: 'Show on map' })).toBeVisible();
  await expect.poll(() => page.evaluate(async () => {
    const source = window.map.getSource('explorer-selection');
    return source ? (await source.getData()).features.length : 0;
  })).toBe(1);
});

test('outside-silhouette articles stay in the list and totals but do not become ocean pins', async ({ page }) => {
  const masked = { ...outside, geometry: { type: 'Point', coordinates: [4.599, 51.90] }, properties: { title: 'Masked-out report' } };
  await page.route('**/api/v1/live?**', route => route.fulfill({ json: { type: 'FeatureCollection', features: [inside, masked], total_count: 2 } }));
  await openMap(page, '/?weather=off');
  await page.getByRole('button', { name: 'Local news', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Local news', exact: true })).toContainText('2 stories · 1 map location');
  await expect(page.getByText('1 mapped; 1 outside current map area.', { exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(async () => {
    const source = window.map.getSource('explore-news');
    return source ? (await source.getData()).features.map(feature => feature.id) : [];
  })).toEqual(['inside-record']);
  await page.getByRole('button', { name: /In view/ }).click();
  await expect(page.locator('.result-row')).toHaveCount(2);
  await expect(page.getByRole('button', { name: /Masked-out report/ })).toContainText('Outside current map area');
});

test('border-crossing roads remain selectable and focus their visible city section', async ({ page }) => {
  const road = { type: 'Feature', id: 'crossing-road', geometry: { type: 'LineString', coordinates: [[4.36, 51.92], [4.49, 51.92]] }, properties: { name: 'Border road example', speed_kmh: 40, congestion_level: 'moderate' } };
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.route('**/api/v1/mobility/traffic?**', route => route.fulfill({ json: { type: 'FeatureCollection', features: [road] } }));
  await openMap(page, '/?weather=off');
  await page.getByRole('button', { name: 'Traffic', exact: true }).click();
  await expect.poll(() => page.evaluate(async () => {
    const source = window.map.getSource('explore-traffic');
    if (!source) return false;
    const geometry = (await source.getData()).features[0]?.geometry;
    const ids = window.map.getStyle().layers.map(layer => layer.id);
    return geometry?.type === 'LineString' && geometry.coordinates[0][0] === 4.36
      && ids.indexOf('explore-traffic-line') < ids.indexOf('rotterdam-water-mask');
  })).toBe(true);
  await page.getByRole('button', { name: /In view/ }).click();
  await page.getByRole('button', { name: /Border road example/ }).click();
  await expect(page.getByRole('region', { name: 'Location details' }).getByRole('button', { name: 'Show on map' })).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.map.getZoom())).toBeGreaterThan(12);
});
