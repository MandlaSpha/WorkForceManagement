import { expect, test } from '@playwright/test'

import { expectNoAccessibilityViolations, PASSWORD, signIn } from './helpers'

/**
 * The restyled Analytics and Reports screens against the real stack: the basis chips stay on
 * the scorecard tiles (DAT-10), and a schedule is created, paused and deleted only after a
 * confirmation.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

test('analytics shows a basis chip on every figure tile', async ({ page }) => {
  await signIn(page, 'executive')
  await page.goto('/analytics')
  const tiles = page.getByTestId('analytics-tiles')
  await expect(tiles).toBeVisible()
  const count = await tiles.locator('li').count()
  expect(count).toBeGreaterThan(0)
  await expect(tiles.getByTestId('basis')).toHaveCount(count)
  await expect(page.getByRole('group', { name: 'Range' })).toBeVisible()
  await expectNoAccessibilityViolations(page)
})

test('a planner schedules a report, pauses it and deletes it after confirming', async ({
  page,
}) => {
  await signIn(page, 'planner')
  await page.goto('/reports')
  const form = page.getByRole('form', { name: 'Schedule a report' })
  await expect(form).toBeVisible()
  await expect(page.getByRole('radiogroup', { name: 'Report type' })).toBeVisible()
  await expectNoAccessibilityViolations(page)

  // Needs an allowed domain; when none is set the form says so and the test stops here.
  if (await page.getByTestId('no-domains').isVisible()) return
  const helper =
    (await form
      .getByText(/One address per line, on /)
      .first()
      .textContent()) ?? ''
  const domain = /on ([\w.-]+?)[.,]/.exec(`${helper},`)?.[1]
  test.skip(!domain, 'No allowed domain could be read from the form.')

  await page.getByRole('radio', { name: /^Investment-board KPI pack/ }).check({ force: true })
  await form.getByLabel(/Send to/).fill(`e2e-${Date.now()}@${domain}`)
  await form.getByRole('button', { name: 'Schedule report' }).click()
  await expect(page.getByTestId('schedule-result')).toBeVisible()

  await page
    .getByRole('button', { name: /^Pause Investment-board KPI pack schedule/ })
    .first()
    .click()
  await expect(
    page.getByRole('button', { name: /^Resume Investment-board KPI pack schedule/ }).first(),
  ).toBeVisible()

  const remove = page
    .getByRole('button', { name: /^Delete Investment-board KPI pack schedule/ })
    .first()
  const before = await page.getByRole('row').count()
  await remove.click()
  await page.getByRole('dialog').getByRole('button', { name: 'Keep it' }).click()
  await expect(page.getByRole('row')).toHaveCount(before)
  await remove.click()
  await page.getByRole('dialog').getByRole('button', { name: 'Delete schedule' }).click()
  await expect(page.getByRole('row')).toHaveCount(before - 1)
})
