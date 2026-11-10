import { test, expect } from '@playwright/test';

const items = ['concert', 'festival', 'theatre', 'exhibition', 'stadium_fixture'].map((subcategory, index) => ({
  type: 'Feature', id: `drawing-${index}`, geometry: { type: 'Point', coordinates: [4.435 + index * 0.025, 51.93] }, properties: { title: `${subcategory} programme`, subcategory }
}));

test('bespoke SVG event markers render as distinct retina symbols and survive style changes', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/v1/events?**', route => route.fulfill({ json: { type: 'FeatureCollection', features: items } }));
  await page.goto('/?weather=off');
  await page.getByRole('button', { name: 'What’s on', exact: true }).click();
  await expect.poll(() => page.evaluate(() => {
    const map = window.map;
    if (!map?.getLayer('explore-events-point')) return 0;
    return map.queryRenderedFeatures({ layers: ['explore-events-point'] }).length;
  })).toBeGreaterThanOrEqual(4);
  const symbols = await page.evaluate(() => {
    const map = window.map;
    const source = map.getSource('explore-events')._data;
    return { type: map.getLayer('explore-events-point').type, kinds: source.features.map(f => f.properties.__markerKind), registered: ['concert', 'festival', 'theatre', 'exhibition', 'football'].every(kind => map.hasImage(`city-mark-${kind}`)) };
  });
  expect(symbols.type).toBe('symbol');
  expect(symbols.kinds).toEqual(['concert', 'festival', 'theatre', 'exhibition', 'football']);
  expect(symbols.registered).toBe(true);
  await page.getByRole('button', { name: 'Map', exact: true }).click();
  await page.getByRole('button', { name: 'Night', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.map.hasImage('city-mark-theatre'))).toBe(true);
  await page.getByRole('button', { name: 'Aerial', exact: true }).click();
  await expect.poll(() => page.evaluate(() => {
    const map = window.map;
    return map.getLayer('explore-events-point') ? map.queryRenderedFeatures({ layers: ['explore-events-point'] }).length : 0;
  })).toBeGreaterThanOrEqual(4);
  expect(errors).toEqual([]);
});

test('every bespoke glyph decodes locally into a visible SVG sprite', async ({ page }) => {
  await page.goto('/?weather=off');
  const result = await page.evaluate(async () => {
    const { ICON_PATHS, markerSvg, rasterizeSymbol } = await import('/src/lib/mapSymbols.js');
    const kinds = ['event', 'concert', 'festival', 'theatre', 'exhibition', 'football', 'bridge', 'camera', 'parking', 'shop', 'bakery', 'pharmacy', 'water', 'toilet', 'aed', 'charging', 'news', 'report', 'leaf', 'works', 'weather', 'cluster'];
    return Promise.all(kinds.map(async kind => {
      const image = await rasterizeSymbol(markerSvg(kind));
      let opaque = 0;
      for (let i = 3; i < image.data.length; i += 4) if (image.data[i] > 200) opaque++;
      return { kind, drawing: kind === 'cluster' || !!ICON_PATHS[kind], visible: opaque / (image.width * image.height) > 0.35, retina: image.width === (kind === 'cluster' ? 108 : 80) };
    }));
  });
  expect(result.every(item => item.drawing && item.visible && item.retina)).toBe(true);
});
