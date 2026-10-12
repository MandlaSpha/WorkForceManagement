import { defineConfig, devices } from '@playwright/test'

/**
 * End-to-end tests run against a full running stack (Aspire locally, Compose in CI).
 *   WFM_BASE_URL       the web app, e.g. http://localhost:5173
 *   WFM_DEMO_PASSWORD  password of the synthetic demo accounts (seed_demo)
 */
export default defineConfig({
  testDir: './tests',
  outputDir: './test-results',
  fullyParallel: false, // the demo accounts share one database and one login lockout counter
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  use: {
    baseURL: process.env.WFM_BASE_URL ?? 'http://localhost:5173',
    trace: 'retain-on-failure',
    reducedMotion: 'reduce', // also proves the app honours prefers-reduced-motion
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] }, grepInvert: /@mobile/ },
    { name: 'mobile', use: { ...devices['Pixel 7'] }, grep: /@mobile/ },
  ],
})
