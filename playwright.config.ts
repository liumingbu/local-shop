import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/e2e', workers: 1, retries: 0,
  use: { baseURL: 'http://127.0.0.1:5173', viewport: {width: 390, height: 844},
         launchOptions: { executablePath: '/usr/bin/chromium' }, screenshot: 'off', trace: 'off' },
  reporter: 'list',
});
