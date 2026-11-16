import { test, expect } from '@playwright/test';
import { openMap } from './navigation.js';

test('a story with no supplied location remains readable without a map pin or camera flight', async ({ page }) => {
  await page.route('**/api/v1/live?**', route => route.fulfill({ json: {
    type: 'FeatureCollection', total_count: 1,
    features: [{ type: 'Feature', id: 'unlocated-story', geometry: null,
      properties: { id: 'unlocated-story', title: 'Citywide report without a supplied location',
        category: 'news', details: { location_precision: 'unknown', link: 'https://news.example/story' } } }]
  } }));
  await openMap(page, '/?weather=off');
  await page.getByRole('button', { name: 'Local news', exact: true }).click();
  await expect(page.getByText('1 record has no reported map location.')).toBeVisible();
  await page.getByRole('button', { name: /In view/ }).click();
  const camera = await page.evaluate(() => window.map.getCenter().toArray());
  await page.getByRole('button').filter({ hasText: 'Citywide report without a supplied location' }).click();
  const details = page.getByRole('region', { name: 'Location details' });
  await expect(details.getByRole('heading')).toHaveText('Citywide report without a supplied location');
  await expect(details.getByText('The source has not provided a map location for this record.')).toBeVisible();
  await expect(details.getByRole('button', { name: 'Show on map' })).toHaveCount(0);
  expect(await page.evaluate(() => window.map.getCenter().toArray())).toEqual(camera);
  expect(await page.evaluate(async () => (await window.map.getSource('explore-news').getData()).features.length)).toBe(0);
});

test('unknown district activity keeps a neutral map color and never becomes a zero score', async ({ page }) => {
  await page.route('**/api/v1/crowd/live?**', route => route.fulfill({ json: {
    type: 'FeatureCollection', features: [{ type: 'Feature', id: 'unknown-district',
      geometry: { type: 'Polygon', coordinates: [[[4.47,51.915],[4.49,51.915],[4.49,51.93],[4.47,51.915]]] },
      properties: { id: 'unknown-district', district_name: 'Centrum', crowd_index: null, crowd_status: 'Unknown' }
    }]
  } }));
  await openMap(page, '/?weather=off');
  await page.getByRole('button', { name: 'City pulse', exact: true }).click();
  await page.getByRole('button', { name: /In view/ }).click();
  await page.getByRole('button').filter({ hasText: 'Unknown' }).last().click();
  const details = page.getByRole('region', { name: 'Location details' });
  await expect(details).toContainText('Unknown');
  await expect(details.locator('.primary-metric')).toHaveCount(0);
  const color = await page.evaluate(() => window.map.getPaintProperty('explore-crowd-fill','fill-color'));
  expect(color[0]).toBe('case');
  expect(color.at(-1)).toBe('#7f8983');
});

test('unverified traffic paths use an approximate location instead of a straight road chord', async ({ page }) => {
  await page.route('**/api/v1/mobility/traffic?**', route => route.fulfill({ json: {
    type:'FeatureCollection',features:[{type:'Feature',id:'approximate-route',
      geometry:{type:'LineString',coordinates:[[4.48,51.92],[4.49,51.91]]},
      properties:{id:'approximate-route',name:'Reported journey with unverified road path',speed_kmh:25,
        speed_measurement_type:'route_average_estimate',geometry_quality:'approximate_route_start',
        display_geometry:{type:'Point',coordinates:[4.48,51.92]}}
    }]
  } }));
  await openMap(page, '/?weather=off');
  await page.getByRole('button', { name:'Traffic',exact:true }).click();
  await expect.poll(() => page.evaluate(async () => (await window.map.getSource('explore-traffic')?.getData())?.features[0]?.geometry.type)).toBe('Point');
  await page.getByRole('button', { name:/In view/ }).click();
  await page.getByRole('button').filter({hasText:'Reported journey with unverified road path'}).click();
  const details=page.getByRole('region',{name:'Location details'});
  await expect(details).toContainText('Estimated route speed');
  await expect(details).toContainText('Approximate route start; road path unverified');
});
