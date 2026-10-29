import { expect, test } from '@playwright/test'

import { expectNoAccessibilityViolations, PASSWORD, signIn, signOut } from './helpers'

test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

const nav = (page: import('@playwright/test').Page) =>
  page.getByRole('navigation', { name: 'Main navigation' })

test.describe('sign-in', () => {
  test('login page renders and is accessible', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByRole('heading', { name: 'Workforce Management' })).toBeVisible()
    await page.screenshot({
      path: 'screenshots/login-light.png',
      fullPage: true,
    })
    await expectNoAccessibilityViolations(page)
  })

  test('a wrong password gets one generic message and stays on the login page', async ({
    page,
  }) => {
    await signIn(page, 'planner', 'definitely-wrong', { expectSuccess: false })
    await expect(page.getByRole('alert')).toHaveText('Username or password is incorrect.')
    await expect(page).toHaveURL(/\/login/)
  })

  test('an anonymous visit to a screen goes to login and comes back after signing in', async ({
    page,
  }) => {
    await page.goto('/forecast')
    await expect(page).toHaveURL(/\/login\?redirect=(%2F|\/)forecast/)
    await page.getByLabel('Username').fill('planner')
    await page.getByLabel('Password').fill(PASSWORD)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page).toHaveURL(/\/forecast$/)
    await expect(page.getByRole('heading', { name: 'Forecast', exact: true })).toBeVisible()
  })
})

test.describe('planner', () => {
  test('sees planning screens but not admin screens, and can sign out', async ({ page }) => {
    await signIn(page, 'planner')

    await expect(
      page.getByRole('heading', { name: /^Good (morning|afternoon|evening)/ }),
    ).toBeVisible()
    await expect(nav(page).getByRole('link', { name: 'Planner' })).toBeVisible()
    await expect(nav(page).getByRole('link', { name: 'Configure' })).toHaveCount(0)
    await expect(nav(page).getByRole('link', { name: 'Audit log' })).toHaveCount(0)
    await page.screenshot({
      path: 'screenshots/dashboard-planner-light.png',
      fullPage: true,
    })
    await expectNoAccessibilityViolations(page)

    await signOut(page)
  })

  test('is told plainly when typing an admin-only address', async ({ page }) => {
    await signIn(page, 'planner')
    await page.goto('/configure')
    await expect(
      page.getByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })
})

test.describe('agent', () => {
  test('lands on their own schedule and cannot reach planning screens', async ({ page }) => {
    await signIn(page, 'agent')

    await expect(page).toHaveURL(/\/my-schedule$/)
    await expect(nav(page).getByRole('link', { name: 'My schedule' })).toBeVisible()
    await expect(nav(page).getByRole('link', { name: 'Planner' })).toHaveCount(0)
    await expect(page.getByLabel('Site')).toHaveCount(0)

    await page.goto('/planner')
    await expect(
      page.getByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })
})

test.describe('admin', () => {
  test('sees configuration and the audit log', async ({ page }) => {
    await signIn(page, 'admin')
    // Admin screens sit under Settings at the foot of the sidebar.
    await nav(page)
      .getByRole('button', { name: /^Settings/ })
      .click()
    await expect(nav(page).getByRole('link', { name: 'Configure' })).toBeVisible()
    await expect(nav(page).getByRole('link', { name: 'Audit log' })).toBeVisible()
  })
})

test.describe('theme', () => {
  test('dark mode applies, stays after a reload, and is accessible', async ({ page }) => {
    await signIn(page, 'planner')
    // The dashboard fetches its figures. Let it finish before switching theme, or the colour
    // check can run while the table is still being drawn.
    await expect(page.getByText(/^Loading/)).toHaveCount(0)
    await page.getByRole('button', { name: 'Switch to dark mode' }).click()
    await expect(page.locator('html')).toHaveClass(/dark/)
    await page.screenshot({
      path: 'screenshots/dashboard-planner-dark.png',
      fullPage: true,
    })
    await expectNoAccessibilityViolations(page)

    await page.reload()
    await expect(page.locator('html')).toHaveClass(/dark/)
    await expect(page.getByRole('button', { name: 'Switch to light mode' })).toBeVisible()
  })
})

test.describe('mobile @mobile', () => {
  test('the navigation opens as a drawer from the menu button', async ({ page }) => {
    await signIn(page, 'planner')

    const menu = page.getByRole('button', { name: 'Open navigation' })
    await expect(menu).toBeVisible()
    await menu.click()
    await expect(nav(page).getByRole('link', { name: 'Roster' })).toBeInViewport({ ratio: 1 })
    await page.screenshot({ path: 'screenshots/dashboard-mobile-drawer.png' })

    await nav(page).getByRole('link', { name: 'Roster' }).click()
    await expect(page.getByRole('heading', { name: 'Roster' })).toBeVisible()
    await expect(nav(page).getByRole('link', { name: 'Roster' })).not.toBeInViewport()
  })
})
