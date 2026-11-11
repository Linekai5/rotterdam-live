import { test, expect } from '@playwright/test';

test('the welcome banner dismisses anywhere without activating the control underneath', async ({ page }) => {
  await page.goto('/?weather=off');
  const notice = page.getByRole('dialog', { name: 'Development notice' });
  await expect(notice).toBeVisible();
  const image = notice.getByRole('img');
  await image.evaluate(element => element.decode());
  expect(await image.evaluate(element => element.naturalWidth)).toBe(1678);

  // Click over the weather card: the first click should only dismiss the notice.
  const weather = page.locator('.weather-hud button').first();
  await expect(weather).toHaveAttribute('aria-expanded', 'true');
  const box = await weather.boundingBox();
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await expect(notice).toHaveCount(0);
  await expect(weather).toHaveAttribute('aria-expanded', 'true');
  await weather.click();
  await expect(weather).toHaveAttribute('aria-expanded', 'false');

  // A fresh entry shows the artwork again, and clicking the artwork also closes it.
  await page.reload();
  await expect(notice).toBeVisible();
  await notice.getByRole('img').click();
  await expect(notice).toHaveCount(0);
  await page.getByRole('button', { name: 'Map', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Aerial', exact: true })).toBeVisible();
});

test('the banner stays centered and compact on desktop, small phones, and landscape screens', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const viewport of [
    { width: 1440, height: 960 },
    { width: 320, height: 740 },
    { width: 844, height: 390 }
  ]) {
    await page.setViewportSize(viewport);
    await page.goto('/?weather=off');
    const notice = page.getByRole('dialog');
    const image = notice.getByRole('img');
    await expect(notice).toBeVisible();
    await image.evaluate(element => element.decode());
    const box = await image.boundingBox();
    expect(box.width).toBeLessThanOrEqual(640);
    expect(box.x).toBeGreaterThanOrEqual(16);
    expect(box.x + box.width).toBeLessThanOrEqual(viewport.width - 16);
    expect(Math.abs(box.x + box.width / 2 - viewport.width / 2)).toBeLessThan(1);
    expect(Math.abs(box.y + box.height / 2 - viewport.height / 2)).toBeLessThan(24);
    expect(box.width / box.height).toBeCloseTo(1678 / 937, 2);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(viewport.width);
    await page.mouse.click(viewport.width - 8, viewport.height - 8);
    await expect(notice).toHaveCount(0);
  }
});

test('the notice supports Dutch, Escape, and keyboard activation', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('rotterdam-live-language', 'nl'));
  await page.goto('/?weather=off');
  const notice = page.getByRole('dialog', { name: 'Ontwikkelingsmelding' });
  await expect(notice).toContainText('Klik ergens om de stad te ontdekken');
  await page.keyboard.press('Escape');
  await expect(notice).toHaveCount(0);
  await page.getByRole('button', { name: 'Kaart', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Luchtfoto', exact: true })).toBeVisible();

  await page.reload();
  await expect(notice.getByRole('button', { name: 'Ontwikkelingsmelding sluiten' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(notice).toHaveCount(0);
});
