import { expect, test, type Page } from '@playwright/test'

import { PASSWORD, signIn } from './helpers'

/**
 * A guided tour, not a check: signs in as every role, visits every screen that role may open and
 * saves a screenshot of each to e2e/screenshots/tour/. Run it to see how far the app has come:
 *   pnpm exec playwright test --project=tour
 * Excluded from the normal run.
 */
const ROLES: Array<{ username: string; role: string; screens: string[] }> = [
  {
    username: 'planner',
    role: 'planner',
    screens: [
      '/',
      '/planner',
      '/intraday',
      '/roster',
      '/forecast',
      '/recommendations',
      '/capacity',
      '/scheduling',
      '/imports',
      '/service-desk',
      '/leave',
      '/shift-swaps',
      '/employees',
      '/overtime',
      '/attendance',
      '/skills',
      '/wellbeing',
      '/analytics',
      '/calibration',
      '/reports',
    ],
  },
  { username: 'lead', role: 'lead', screens: ['/', '/roster', '/leave', '/overtime', '/reports'] },
  { username: 'agent', role: 'agent', screens: ['/my-schedule', '/my-availability', '/leave'] },
  {
    username: 'admin',
    role: 'admin',
    screens: ['/', '/configure', '/audit', '/planner', '/imports'],
  },
  {
    username: 'executive',
    role: 'executive',
    screens: ['/', '/capacity', '/analytics', '/reports'],
  },
  { username: 'customerops', role: 'customer_ops', screens: ['/', '/capacity', '/service-desk'] },
]

const name = (path: string) => (path === '/' ? 'home' : path.slice(1).replaceAll('/', '-'))

async function shot(page: Page, file: string): Promise<void> {
  // Let screens that fetch data finish, so the picture shows the screen and not "Loading…".
  await page
    .getByText(/^Loading/)
    .first()
    .waitFor({ state: 'detached', timeout: 5000 })
    .catch(() => undefined)
  await page.screenshot({ path: `screenshots/tour/${file}.png`, fullPage: false })
}

for (const { username, role, screens } of ROLES) {
  test(`@tour ${role}: every screen`, async ({ page }) => {
    await signIn(page, username)
    for (const path of screens) {
      await page.goto(path)
      await expect(page.getByRole('main')).toBeVisible()
      await shot(page, `${role}--${name(path)}`)
    }
  })
}

test('@tour a role is shown the access-denied page', async ({ page }) => {
  await signIn(page, 'agent')
  await page.goto('/planner')
  await expect(
    page.getByRole('heading', { name: "You don't have access to this page" }),
  ).toBeVisible()
  await shot(page, 'agent--forbidden')
})

test('@tour login, dark mode and the directory option', async ({ page }) => {
  await page.goto('/login')
  await shot(page, 'login--light')
  await page.getByRole('button', { name: 'Switch to dark mode' }).click()
  await expect(page.locator('html')).toHaveClass(/dark/)
  await page.waitForTimeout(300) // let the repaint finish before the picture is taken
  await shot(page, 'login--dark')
  await page.getByRole('button', { name: 'Switch to light mode' }).click()
  await page.getByLabel('Sign in with').selectOption({ label: 'Company directory' })
  await page.getByLabel('Username').fill('pat')
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(
    page.getByRole('heading', { name: /^Good (morning|afternoon|evening)/ }),
  ).toBeVisible()
  await shot(page, 'directory-planner--home')
})

test('@tour the phone layout', async ({ browser }) => {
  const context = await browser.newContext({
    viewport: { width: 412, height: 915 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
  })
  const page = await context.newPage()
  await signIn(page, 'planner')
  await shot(page, 'mobile--home')
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.waitForTimeout(400)
  await shot(page, 'mobile--drawer')
  await context.close()
})
