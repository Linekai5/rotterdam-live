import { test, expect } from '@playwright/test';
const feature = { type: 'Feature', id: 'test-event', geometry: { type: 'Point', coordinates: [4.48, 51.92] }, properties: { title: 'An evening by the Maas', venue_name: 'Rotterdam Centrum', description: 'A local programme along the river.' } };
test('layers load on demand, show selectable results, and clear from the map', async ({ page }) => {
  let requests = 0;
  await page.route('**/api/v1/events?**', route => { requests++; return route.fulfill({ json: { type: 'FeatureCollection', features: [feature] } }); });
  await page.goto('/?weather=off');
  await expect(page.getByRole('heading', { name: 'Explore Rotterdam.' })).toBeVisible();
  expect(requests).toBe(0);
  await page.getByRole('button', { name: 'What’s on', exact: true }).click();
  await expect(page.getByRole('button', { name: 'What’s on', exact: true })).toContainText('1 in this view');
  expect(requests).toBe(1);
  await expect.poll(() => page.evaluate(() => !!window.map.getLayer('explore-events-point'))).toBe(true);
  await page.getByRole('button', { name: /In view/ }).click();
  await page.getByRole('button', { name: /An evening by the Maas/ }).click();
  await expect(page.getByRole('region', { name: 'Location details' })).toContainText('A local programme');
  await page.getByRole('button', { name: 'Close location details' }).click();
  await page.getByRole('button', { name: 'Clear all' }).click();
  await expect.poll(() => page.evaluate(() => !!window.map.getSource('explore-events'))).toBe(false);
});
test('mobile explorer opens and unavailable layers explain their state', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route('**/api/v1/events?**', route => route.fulfill({ status: 503, json: { detail: 'Unavailable' } }));
  await page.goto('/?weather=off');
  await page.getByRole('button', { name: /Explore the city/ }).click();
  await page.getByRole('button', { name: 'What’s on', exact: true }).click();
  await expect(page.getByRole('button', { name: 'What’s on', exact: true })).toContainText('unavailable');
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
});

test('facility filters request only the chosen category and preserve zero availability in details', async ({ page }) => {
  const categories = [];
  await page.route('**/api/v1/amenities?**', route => {
    const category = new URL(route.request().url()).searchParams.get('subcategory'); categories.push(category);
    return route.fulfill({ json: { type: 'FeatureCollection', features: [{ ...feature, id: category, properties: { title: category === 'toilet' ? 'Public toilet by the river' : 'Public water tap', subcategory: category, details: { wheelchair_accessible: false, free_water: category === 'water_tap' } } }] } });
  });
  await page.route('**/api/v1/mobility?**', route => route.fulfill({ json: { type: 'FeatureCollection', features: [{ ...feature, id: 'parking', properties: { title: 'Riverside parking', subcategory: 'parking', details: { available_spaces: 0, total_capacity: 100, occupancy_rate: 100 } } }] } }));
  await page.goto('/?weather=off');
  await page.getByRole('button', { name: 'Useful places', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Useful places', exact: true })).toContainText('1 in this view');
  await page.getByLabel('Useful places: Facility').selectOption('toilet');
  await expect.poll(() => categories).toEqual(['water_tap', 'toilet']);
  await page.getByRole('button', { name: /Explore useful places/ }).click();
  await page.getByRole('button', { name: /Public toilet by the river/ }).click();
  await expect(page.getByRole('region', { name: 'Location details' })).toContainText('Not listed as accessible');
  await page.getByRole('button', { name: 'Close location details' }).click();
  await page.getByRole('button', { name: /Map layers/ }).click();
  await page.getByRole('button', { name: 'Parking', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Parking', exact: true })).toContainText('1 in this view');
  await page.getByRole('button', { name: /Explore parking/ }).click();
  await page.getByRole('button', { name: /Riverside parking/ }).click();
  await expect(page.getByRole('region', { name: 'Location details' })).toContainText('0 spaces');
});

test('changing map styles preserves selected overlays and preferences without fetching every dataset', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  let requests = 0;
  await page.route('**/api/v1/events?**', route => { requests++; return route.fulfill({ json: { type: 'FeatureCollection', features: [feature] } }); });
  await page.goto('/?weather=off');
  await page.getByRole('button', { name: 'What’s on', exact: true }).click();
  await expect(page.getByRole('button', { name: 'What’s on', exact: true })).toContainText('1 in this view');
  await page.getByRole('button', { name: 'Map', exact: true }).click();
  await page.getByRole('switch', { name: 'Place names', exact: true }).click();
  await page.getByRole('button', { name: 'Night', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.map.getStyle().layers.some(l => l.id === 'explore-events-point'))).toBe(true);
  await expect.poll(() => page.evaluate(() => window.map.queryRenderedFeatures({ layers: ['explore-events-point'] }).length)).toBeGreaterThan(0);
  await page.getByRole('button', { name: /Map layers/ }).click();
  await page.getByRole('button', { name: 'Map', exact: true }).click();
  await expect(page.getByRole('switch', { name: 'Place names', exact: true })).toHaveAttribute('aria-checked', 'false');
  await page.getByRole('button', { name: 'Aerial', exact: true }).click();
  await expect.poll(() => page.evaluate(() => !!window.map.getLayer('explore-events-point'))).toBe(true);
  await expect.poll(() => page.evaluate(() => window.map.queryRenderedFeatures({ layers: ['explore-events-point'] }).length)).toBeGreaterThan(0);
  expect(errors).toEqual([]);
  expect(requests).toBe(1);
});

test('search supports keyboard selection and district profiles load only on request', async ({ page }) => {
  let profiles = 0;
  await page.route('**/api/v1/search?**', route => route.fulfill({ json: { type: 'FeatureCollection', features: [{ ...feature, properties: { title: 'Erasmusbrug', district: 'Rotterdam Centrum', entity_type: 'address' } }] } }));
  await page.route('**/api/v1/living/districts/**/passport', route => {
    profiles++;
    return route.fulfill({ json: { type: 'Feature', geometry: feature.geometry, properties: { district_name: 'Rotterdam Centrum', demographics: { data_year: 2026, total_population: 42925, source: 'CBS' }, housing: { surface_area: { average_m2: 82.5 } } } } });
  });
  await page.goto('/?weather=off');
  await page.getByRole('textbox', { name: 'Search Rotterdam' }).fill('Erasmus');
  await expect(page.getByRole('button', { name: /Erasmusbrug/ })).toBeVisible();
  await page.getByRole('textbox', { name: 'Search Rotterdam' }).press('ArrowDown');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('region', { name: 'Location details' })).toContainText('Erasmusbrug');
  expect(profiles).toBe(0);
  await page.getByRole('button', { name: 'Explore this district' }).click();
  await expect(page.getByRole('region', { name: 'District profile' })).toContainText('42,925');
  expect(profiles).toBe(1);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('region', { name: 'Location details' })).toHaveCount(0);
});

test('radar stays unloaded until enabled and can be removed independently of clouds', async ({ page }) => {
  let radarRequests = 0;
  await page.route('**/api/v1/weather/radar', route => {
    radarRequests++;
    return route.fulfill({ json: { latest_frame: { time: Math.floor(Date.now()/1000), tile_url: 'https://tilecache.rainviewer.com/v2/radar/test/512/{z}/{x}/{y}/2/1_1.png' } } });
  });
  await page.route('https://tilecache.rainviewer.com/**', route => route.abort());
  await page.goto('/?weather=off');
  await page.getByRole('button', { name: 'Map', exact: true }).click();
  expect(radarRequests).toBe(0);
  await page.getByRole('switch', { name: 'Rain radar', exact: true }).click();
  await expect.poll(() => radarRequests).toBe(1);
  await expect.poll(() => page.evaluate(() => !!window.map.getLayer('live-rain-radar'))).toBe(true);
  await page.getByRole('switch', { name: 'Rain radar', exact: true }).click();
  await expect.poll(() => page.evaluate(() => !!window.map.getSource('live-rain-radar'))).toBe(false);
  await expect(page.getByRole('switch', { name: 'Cloud atmosphere', exact: true })).toHaveAttribute('aria-checked', 'false');
});

test('dense point layers cluster and expand when a cluster is selected', async ({ page }) => {
  await page.route('**/api/v1/events?**', route => route.fulfill({ json: { type: 'FeatureCollection', features: Array.from({length:8}, (_,i) => ({ ...feature, id: `event-${i}`, geometry: { type: 'Point', coordinates: [4.48 + i*0.00005,51.92] } })) } }));
  await page.goto('/?weather=off');
  await page.getByRole('button', { name: 'What’s on', exact: true }).click();
  await expect.poll(() => page.evaluate(() => {
    if (!window.map.getLayer('explore-events-cluster')) return 0;
    return window.map.queryRenderedFeatures({ layers: ['explore-events-cluster'] }).length;
  })).toBeGreaterThan(0);
  const cluster = await page.evaluate(() => {
    const f = window.map.queryRenderedFeatures({ layers: ['explore-events-cluster'] })[0];
    const p = window.map.project(f.geometry.coordinates); return { x: p.x, y: p.y, zoom: window.map.getZoom() };
  });
  await page.mouse.click(cluster.x, cluster.y);
  await expect.poll(() => page.evaluate(() => window.map.getZoom())).toBeGreaterThan(cluster.zoom);
});

test('mobile selection returns to results and reopening the explorer dismisses the detail sheet', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route('**/api/v1/events?**', route => route.fulfill({ json: { type: 'FeatureCollection', features: [feature] } }));
  await page.goto('/?weather=off');
  await page.getByRole('button', { name: /Explore the city/ }).click();
  await page.getByRole('button', { name: 'What’s on', exact: true }).click();
  await expect(page.getByRole('button', { name: 'What’s on', exact: true })).toContainText('1 in this view');
  await page.getByRole('button', { name: /In view/ }).click();
  await page.getByRole('button', { name: /An evening by the Maas/ }).click();
  await expect(page.getByRole('complementary', { name: 'City explorer' })).toBeHidden();
  await expect(page.getByRole('region', { name: 'Location details' })).toBeVisible();
  await page.getByRole('button', { name: 'Close location details' }).click();
  await expect(page.getByRole('complementary', { name: 'City explorer' })).toBeVisible();
  await page.getByRole('button', { name: /An evening by the Maas/ }).click();
  await page.getByRole('button', { name: /Explore the city/ }).click();
  await expect(page.getByRole('region', { name: 'Location details' })).toHaveCount(0);
  await expect(page.getByRole('complementary', { name: 'City explorer' })).toBeVisible();
});

test('reduced motion skips panel/camera animation and keyboard shortcuts remain usable', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.route('**/api/v1/search?**', route => route.fulfill({ json: { type: 'FeatureCollection', features: [{ ...feature, properties: { title: 'Erasmusbrug', district: 'Rotterdam Centrum' } }] } }));
  await page.goto('/?weather=off');
  await page.keyboard.press('Control+k');
  await expect(page.getByRole('textbox', { name: 'Search Rotterdam' })).toBeFocused();
  await page.getByRole('textbox', { name: 'Search Rotterdam' }).fill('Erasmus');
  await page.getByRole('button', { name: /Erasmusbrug/ }).click();
  await expect(page.getByRole('region', { name: 'Location details' })).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.map.isMoving())).toBe(false);
  expect(await page.locator('.explorer').evaluate(node => getComputedStyle(node).animationName)).toBe('none');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('region', { name: 'Location details' })).toHaveCount(0);
});

test('the desktop explorer can collapse without disabling overlays, and search reopens it', async ({ page }) => {
  await page.route('**/api/v1/events?**', route => route.fulfill({ json: { type: 'FeatureCollection', features: [feature] } }));
  await page.goto('/?weather=off');
  await page.getByRole('button', { name: 'What’s on', exact: true }).click();
  await expect(page.getByRole('button', { name: 'What’s on', exact: true })).toContainText('1 in this view');
  await page.getByRole('button', { name: 'Hide explorer', exact: true }).click();
  await expect(page.getByRole('complementary', { name: 'City explorer' })).toBeHidden();
  expect(await page.evaluate(() => !!window.map.getLayer('explore-events-point'))).toBe(true);
  await page.keyboard.press('Control+k');
  await expect(page.getByRole('textbox', { name: 'Search Rotterdam' })).toBeFocused();
  await expect(page.getByRole('complementary', { name: 'City explorer' })).toBeVisible();
});

test('category navigation stays idle and camera filters request mapped locations with honest source details', async ({ page }) => {
  const requests = [];
  await page.route('**/api/v1/amenities/cameras?**', route => {
    const params = new URL(route.request().url()).searchParams;
    requests.push(Object.fromEntries(params));
    return route.fulfill({ json: { type: 'FeatureCollection', features: [{ ...feature, id: 'osm-camera', properties: { title: 'Mapped traffic camera', subcategory: 'camera', details: { camera_type: 'traffic', has_live_feed: false, operator: 'Municipal source', source_url: 'https://www.openstreetmap.org/node/1234', location_basis: 'osm_camera_tag' } } }] } });
  });
  await page.goto('/?weather=off');
  await page.getByRole('button', { name: 'Move', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Traffic', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'What’s on', exact: true })).toHaveCount(0);
  expect(requests).toHaveLength(0);
  await page.getByRole('button', { name: 'City', exact: true }).click();
  await page.getByRole('button', { name: 'Cameras', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Cameras', exact: true })).toContainText('1 in this view');
  expect(requests).toHaveLength(1);
  expect(requests[0].camera_type).toBeUndefined();
  await page.getByLabel('Cameras: Camera type').selectOption('traffic');
  await expect.poll(() => requests.at(-1).camera_type).toBe('traffic');
  await page.getByRole('button', { name: 'Explore cameras', exact: true }).click();
  await page.getByRole('button', { name: /Mapped traffic camera/ }).click();
  const details = page.getByRole('region', { name: 'Location details' });
  await expect(details).toContainText('No public feed listed');
  await expect(details.getByRole('link', { name: 'View mapped source' })).toHaveAttribute('href', 'https://www.openstreetmap.org/node/1234');
  await expect(details.getByRole('link', { name: 'Open public camera' })).toHaveCount(0);
});

test('map glyph hover previews the place without opening or fetching its details', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/v1/mobility?**', route => route.fulfill({ json: { type: 'FeatureCollection', features: [{ ...feature, id: 'bridge', properties: { title: 'Erasmusbrug', subcategory: 'bridge', details: { active_opening: false } } }] } }));
  await page.goto('/?weather=off');
  await page.getByRole('button', { name: 'Bridges', exact: true }).click();
  await expect.poll(() => page.evaluate(() => {
    if (!window.map.getLayer('explore-bridges-point')) return 0;
    return window.map.queryRenderedFeatures({ layers: ['explore-bridges-point'] }).length;
  })).toBeGreaterThan(0);
  const point = await page.evaluate(() => { const p = window.map.project([4.48, 51.92]); return { x: p.x, y: p.y - 14 }; });
  await page.mouse.move(point.x, point.y);
  await expect(page.locator('.map-tooltip')).toContainText('Erasmusbrug');
  await expect(page.getByRole('region', { name: 'Location details' })).toHaveCount(0);
  await page.mouse.move(1100, 800);
  await expect(page.locator('.map-tooltip')).toHaveCount(0);
  await page.mouse.click(point.x, point.y);
  const details = page.getByRole('region', { name: 'Location details' });
  await expect(details.getByRole('button', { name: 'Show on map' })).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.map.getSource('explorer-selection')?._data.features[0]?.geometry?.type)).toBe('Point');
  expect(errors).toEqual([]);
});
