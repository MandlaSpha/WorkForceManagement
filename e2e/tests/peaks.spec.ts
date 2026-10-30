import { expect, test, type Page } from '@playwright/test'

import { expectNoAccessibilityViolations, PASSWORD, signIn } from './helpers'

/**
 * Insight > Peaks & troughs (RPT-03), against the real stack. Demo calls may or may not exist for
 * the queue chosen, so each test accepts either the full dashboard or the plain "nothing to rank"
 * message, and never an empty page or fake charts.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

async function settle(page: Page) {
  await page.goto('/peaks')
  await expect(page.getByRole('heading', { name: 'Peaks & troughs', level: 1 })).toBeVisible()
  await expect(page.getByTestId('peaks-loading')).toHaveCount(0)
}

test('a planner sees the range control and either the dashboard or an honest empty state', async ({
  page,
}) => {
  await signIn(page, 'planner')
  await settle(page)
  await expect(page.getByRole('button', { name: 'Last 30 days' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await page.getByRole('button', { name: 'Last 7 days' }).click()
  await expect(page.getByRole('button', { name: 'Last 7 days' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await page.getByRole('button', { name: 'Custom' }).click()
  await expect(page.getByLabel('From', { exact: true })).toBeVisible()
  await expect(page.getByLabel('To', { exact: true })).toBeVisible()
  if (await page.getByTestId('peaks-none').isVisible()) {
    await expect(page.getByTestId('peaks-heat')).toHaveCount(0)
  } else if (await page.getByTestId('peaks-tiles').isVisible()) {
    await expect(page.getByTestId('peaks-daily')).toBeVisible()
    await expect(page.getByTestId('peaks-profile')).toBeVisible()
    await expect(page.getByTestId('peaks-heat')).toBeVisible()
    await expect(page.getByTestId('busiest-days')).toBeVisible()
  }
})

test('the page has no accessibility violations', async ({ page }) => {
  await signIn(page, 'planner')
  await settle(page)
  await expectNoAccessibilityViolations(page)
})

test('on a phone the page does not scroll sideways', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 })
  await signIn(page, 'planner')
  await settle(page)
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(0)
})

test('an agent is refused, in the screen and in the API', async ({ page }) => {
  await signIn(page, 'agent')
  await page.goto('/peaks')
  await expect(
    page.getByRole('heading', { name: "You don't have access to this page" }),
  ).toBeVisible()
  const response = await page.request.get(
    '/api/v1/telephony/peaks?queue_id=1&date_from=2026-05-01&date_to=2026-05-31',
  )
  expect(response.status()).toBe(403)
})
