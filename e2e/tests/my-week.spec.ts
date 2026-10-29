import { expect, test } from '@playwright/test'

import { expectNoAccessibilityViolations, PASSWORD, signIn } from './helpers'

/**
 * The week calendar on My schedule (UI restyle, stage 2). It shows only what the schedule API
 * already returns, so the checks are about the screen, not about particular shifts.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

test('the agent switches between the week calendar and the agenda list', async ({ page }) => {
  await signIn(page, 'agent')
  await page.goto('/my-schedule')
  await expect(page.getByRole('heading', { name: 'My schedule' })).toBeVisible()

  await page.getByRole('button', { name: 'Week', exact: true }).click()
  await expect(page.getByTestId('week-grid')).toBeVisible()
  await expect(page.getByTestId('week-glance')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Week at a glance' })).toBeVisible()
  await expect(page.getByTestId('glance-shifts')).toBeVisible()
  await expectNoAccessibilityViolations(page)

  await page.getByRole('button', { name: 'Next week' }).click()
  await page.getByRole('button', { name: 'This week' }).click()

  await page.getByRole('button', { name: 'List' }).click()
  await expect(page.getByTestId('week-grid')).toHaveCount(0)
})

test.describe('on a phone @mobile', () => {
  test('there is no Week button and the page stays on the list', async ({ page }) => {
    await signIn(page, 'agent')
    await page.goto('/my-schedule')
    await expect(page.getByRole('button', { name: 'Week', exact: true })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'List' })).toHaveAttribute('aria-pressed', 'true')
  })
})
