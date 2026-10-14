import { defineConfig, devices } from '@playwright/test'

/**
 * End-to-end tests run against a full running stack (Aspire locally, Compose in CI).
 *   WFM_BASE_URL       the web app, e.g. http://localhost:5173
 *   WFM_DEMO_PASSWORD  password of the synthetic demo accounts (seed_demo)
 */
export default defineConfig({
  testDir: './tests',
  outputDir: './test-results',
  // Spec files run side by side; the tests inside one file stay in order. Each spec works on its
  // own queue and on dates no other spec uses, so they do not meet. Set E2E_WORKERS=1 to run
  // them one at a time when chasing a failure.
  fullyParallel: false,
  workers: Number(process.env.E2E_WORKERS ?? 4),
  // Pages are slower when four specs share the stack, so every wait is allowed 15 seconds.
  expect: { timeout: 15_000 },
  retries: 1, // a test that needed the retry is listed as "flaky", so it is not hidden
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  use: {
    baseURL: process.env.WFM_BASE_URL ?? 'http://localhost:5173',
    trace: 'retain-on-failure',
    reducedMotion: 'reduce', // also proves the app honours prefers-reduced-motion
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] }, grepInvert: /@mobile|@tour/ },
    { name: 'mobile', use: { ...devices['Pixel 7'] }, grep: /@mobile/ },
    // On demand only: `playwright test --project=tour` saves a screenshot of every screen per role.
    { name: 'tour', use: { ...devices['Desktop Chrome'] }, grep: /@tour/ },
  ],
})
