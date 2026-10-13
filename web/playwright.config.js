import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  timeout: 45000,
  workers: 1,
  use: {
    channel: 'chrome',
    baseURL: 'http://localhost:5173',
    viewport: { width: 1200, height: 900 },
    screenshot: 'only-on-failure'
  },
  webServer: { command: 'npm run dev -- --host 127.0.0.1', url: 'http://localhost:5173', reuseExistingServer: true }
});
