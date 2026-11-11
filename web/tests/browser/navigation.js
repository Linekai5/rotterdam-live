import { expect } from '@playwright/test';

export async function dismissWelcome(page) {
  const notice = page.locator('dialog[open]');
  await expect(notice).toBeVisible();
  await notice.getByRole('button').click({ position: { x: 8, y: 8 } });
  await expect(page.locator('dialog')).toHaveCount(0);
}

export async function openMap(page, url) {
  const response = await page.goto(url);
  await dismissWelcome(page);
  return response;
}
