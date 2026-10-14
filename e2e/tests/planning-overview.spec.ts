import { expect, test } from '@playwright/test'

import {
  expectNoAccessibilityViolations,
  importDay,
  nextMonday,
  PASSWORD,
  signIn,
  signOut,
} from './helpers'
import { addDays, rand } from './report'

/**
 * The planning overview on the dashboard, against the real stack.
 *
 * The same hand-worked queue as the forecast spec: 10 calls at 10:00 on two Mondays, so the
 * Monday after needs 5 people to roster at 10:00. With nobody rostered that is one half-hour
 * short by 5: gap 5, one under-staffed interval of the 48 the forecast covers, worst -5 at 10:00.
 * Other specs leave their own queues in the shared database, so the test reads only this queue's
 * row and attention item.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

test('a published forecast shows up as a gap on the dashboard, and opens the queue in the planner', async ({
  page,
}) => {
  test.setTimeout(120_000)
  const queue = `E2E Queue o${rand(1_000_000)}`
  const target = nextMonday()

  await signIn(page, 'planner')
  await importDay(page, addDays(target, -14), queue)
  await importDay(page, addDays(target, -7), queue)

  // Run and publish the forecast for the target Monday.
  await page.getByRole('link', { name: 'Forecast' }).click()
  const run = page.getByRole('form', { name: 'Run a forecast' })
  await run.getByLabel('Queue').selectOption({ label: queue })
  await run.getByLabel('Model').selectOption('baseline')
  await run.getByLabel('From').fill(target)
  await run.getByLabel('To').fill(target)
  await run.getByLabel('Label (optional)').fill('e2e overview')
  await run.getByRole('button', { name: 'Run forecast' }).click()
  await expect(page.getByTestId('max-required')).toHaveText('5')
  const versions = page.getByRole('table', { name: 'Versions' })
  await versions.getByRole('button', { name: /Publish e2e overview/ }).click()
  await expect(versions.getByText('published')).toBeVisible()

  // The dashboard, on the week of that Monday.
  await page.getByRole('link', { name: 'Dashboard' }).click()
  await expect(page.getByRole('heading', { name: /^Planning, week of/ })).toBeVisible()
  await page.getByRole('button', { name: 'Next week' }).click()

  const row = page.getByTestId('queue-table').getByRole('row', { name: new RegExp(queue) })
  await expect(row.locator('[data-col="gap"]')).toHaveText('5')
  await expect(row.locator('[data-col="under"]')).toHaveText('1 of 48')
  await expect(row.locator('[data-col="worst"]')).toContainText('−5 at 10:00')
  await expect(row.locator('[data-col="roster"]')).toHaveText('draft')

  // It is on the attention list, with the exact count and a way to open it.
  const attention = page.getByTestId('attention')
  await expect(attention.getByText(`${queue}: 1 under-staffed interval`)).toBeVisible()
  await expectNoAccessibilityViolations(page)
  await page.getByRole('button', { name: 'Switch to dark mode' }).click()
  await expect(page.locator('html')).toHaveClass(/dark/)
  await expectNoAccessibilityViolations(page)
  await page.getByRole('button', { name: 'Switch to light mode' }).click()

  // Choosing the queue opens the planner on it, showing the same -5 at 10:00.
  await row.getByRole('button', { name: `Open the planner for ${queue}` }).click()
  await expect(page).toHaveURL(/\/planner/)
  await expect(page.getByTestId(`cell-${target}-20`)).toHaveText('−5')
})

test('leads see the overview; executives and agents do not, in the screen or in the API', async ({
  page,
}) => {
  await signIn(page, 'lead')
  await expect(page.getByRole('heading', { name: /^Planning, week of/ })).toBeVisible()
  await signOut(page)

  await signIn(page, 'executive')
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
  await expect(page.getByRole('heading', { name: /^Planning, week of/ })).toHaveCount(0)
  const week = nextMonday()
  const refused = await page.request.get(`/api/v1/scheduling/overview?week_start=${week}`)
  expect(refused.status()).toBe(403)
})
