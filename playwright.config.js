const { defineConfig } = require('@playwright/test');

const port = Number(process.env.GRAVITY_E2E_PORT || 8791);
const baseURL = `http://127.0.0.1:${port}`;
const python = process.env.GRAVITY_E2E_PYTHON || 'python';

const managedWebServer = {
  command: `"${python}" -m server.gravity --port ${port}`,
  url: `${baseURL}/api/health`,
  timeout: 30_000,
  reuseExistingServer: false,
  env: {
    ...process.env,
    GRAVITY_ENV: 'development',
    GRAVITY_HOST: '127.0.0.1',
    GRAVITY_PORT: String(port),
    APP_BASE_URL: baseURL,
    GRAVITY_DATA_DIR: '.gravity/e2e/data',
    GRAVITY_LOG_DIR: '.gravity/e2e/logs',
    GRAVITY_BACKUP_DIR: '.gravity/e2e/backups',
    GRAVITY_LOG_LEVEL: 'WARNING',
    SECRET_KEY: 'gravity-e2e-secret-key-with-more-than-thirty-two-bytes',
    FIREBASE_PROJECT_ID: '',
    FIREBASE_WEB_API_KEY: '',
    FIREBASE_AUTH_DOMAIN: '',
    FIREBASE_APP_ID: '',
    RAZORPAY_KEY_ID: '',
    RAZORPAY_KEY_SECRET: '',
    RAZORPAY_WEBHOOK_SECRET: '',
  },
};

module.exports = defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  expect: { timeout: 8_000 },
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [['line'], ['html', { open: 'never' }]] : 'line',
  outputDir: '.gravity/playwright-artifacts',
  use: {
    baseURL,
    browserName: 'chromium',
    colorScheme: 'dark',
    locale: 'en-IN',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: process.env.GRAVITY_E2E_EXTERNAL_SERVER ? undefined : managedWebServer,
});
