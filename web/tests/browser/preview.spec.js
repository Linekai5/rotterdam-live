import { test, expect } from '@playwright/test';

test('the built preview serves its API on the same origin without localhost CORS failures', async ({ browser }) => {
  const origin = process.env.WEB_PREVIEW_ORIGIN;
  test.skip(!origin, 'Set WEB_PREVIEW_ORIGIN after building the local Docker web service.');
  const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
  const calls = [];
  const errors = [];
  page.on('request', request => {
    const url = new URL(request.url());
    if (url.pathname.startsWith('/api/v1/') || url.pathname === '/health/live') calls.push(url);
  });
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto(origin);
    await expect(page.getByRole('heading', { name: 'Explore Rotterdam.' })).toBeVisible();
    const health = await page.request.get(`${origin}/health/live`);
    expect(health.status()).toBe(200);
    expect((await health.json()).status).toBe('alive');
    await page.getByRole('button', { name: 'Traffic', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Traffic', exact: true })).toContainText(/\d+ in this view/);
    await expect.poll(() => page.evaluate(() => !!window.map.getSource('explore-traffic'))).toBe(true);
    expect(calls.some(url => url.pathname === '/api/v1/weather/live')).toBe(true);
    expect(calls.some(url => url.pathname === '/api/v1/mobility/traffic')).toBe(true);
    expect(calls.every(url => url.origin === new URL(origin).origin)).toBe(true);
    expect(errors).toEqual([]);
  } finally { await page.close(); }
});
