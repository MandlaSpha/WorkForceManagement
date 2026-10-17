import { expect, test, type Page } from '@playwright/test'

import { expectNoAccessibilityViolations, importDay, PASSWORD, signIn } from './helpers'
import { addDays, rand, randomMonday } from './report'

/**
 * The forecast over a week and a month, and taking a forecast out of use (Day / Week / Month
 * switch; Discard and Archive).
 *
 * Two Mondays a week apart with 10 answered calls at 10:00 are imported into a queue made up for
 * this run, and the Monday after is forecast (as in forecast.spec.ts): 10 calls at 10:00, 5 agents
 * to roster, so that Monday needs 5 people at the peak and 5 x 0.5 = 2.5 agent-hours. The other
 * six days of its week were never forecast, so they must say "No forecast", not zero.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

async function runForecast(page: Page, queue: string, day: string, label: string): Promise<void> {
  await page.getByRole('link', { name: 'Forecast' }).click()
  const form = page.getByRole('form', { name: 'Run a forecast' })
  await form.getByLabel('Queue').selectOption({ label: queue })
  await form.getByLabel('From').fill(day)
  await form.getByLabel('To').fill(day)
  await form.getByLabel('Label (optional)').fill(label)
  await form.getByRole('button', { name: 'Run forecast' }).click()
  await expect(page.getByRole('heading', { name: `${queue}: ${label}` })).toBeVisible()
}

test('a planner reads the forecast as a week and a month, and opens a day from them', async ({
  page,
}) => {
  const queue = `E2E Queue v${rand(1_000_000)}`
  const monday = randomMonday()
  const target = addDays(monday, 14)
  await signIn(page, 'planner')
  await importDay(page, monday, queue)
  await importDay(page, addDays(monday, 7), queue)
  await runForecast(page, queue, target, 'e2e views')

  // Week: one table row per day, the forecast day worked out by hand, the rest plainly absent.
  await page.getByRole('button', { name: 'Week', exact: true }).click()
  await expect(page).toHaveURL(/view=week/)
  const week = page.getByTestId('week-table')
  const forecastRow = week.getByRole('row').filter({ hasText: /\b5\b/ }).first()
  await expect(forecastRow).toContainText('10.0')
  await expect(forecastRow).toContainText('2.5')
  await expect(week.getByText('No forecast for this day')).toHaveCount(6)
  await expect(page.getByTestId('partial-notice')).toContainText('6 of 7 days have no forecast')
  // What the figures rest on, and that this draft is not live.
  await expect(page.getByTestId('range-basis')).toContainText('a draft that is not live')
  // The heat-grid and the daily chart are there and described.
  await expect(page.getByTestId('heat-grid')).toBeVisible()
  await expect(page.getByRole('img', { name: /Expected calls per day/ })).toBeVisible()
  await expectNoAccessibilityViolations(page)

  // Month: a calendar with the same day, then back down into the day.
  await page.getByRole('button', { name: 'Month', exact: true }).click()
  await expect(page).toHaveURL(/view=month/)
  await expect(page.getByTestId('month-grid')).toBeVisible()
  await expect(page.getByTestId('holiday-note')).toContainText('Public holidays are not recorded')
  await page.getByTestId('month-grid').locator(`[data-day="${target}"]`).click()
  await expect(page.getByRole('button', { name: 'Day', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await expect(page.getByTestId('total-calls')).toHaveText('10.0')

  // The view is in the address, so a reload lands on the same week.
  await page.getByRole('button', { name: 'Week', exact: true }).click()
  await page.reload()
  await expect(page.getByTestId('week-table')).toBeVisible()
})

test('a planner discards a draft and withdraws the live forecast, each with a reason', async ({
  page,
}) => {
  const queue = `E2E Queue r${rand(1_000_000)}`
  const monday = randomMonday()
  const target = addDays(monday, 14)
  await signIn(page, 'planner')
  await importDay(page, monday, queue)
  await importDay(page, addDays(monday, 7), queue)
  await runForecast(page, queue, target, 'to discard')

  // Discard: asks first, needs a reason, then the draft is gone.
  const versions = page.getByRole('table', { name: 'Versions' })
  await versions.getByRole('button', { name: /Discard to discard/ }).click()
  const discard = page.getByRole('form', { name: 'Discard to discard' })
  await expect(discard).toContainText('cannot be undone')
  await expect(discard.getByRole('button', { name: /Confirm: discard/ })).toBeDisabled()
  await discard.getByLabel(/Reason/).fill('e2e: wrong range')
  await discard.getByRole('button', { name: /Confirm: discard/ }).click()
  await expect(page.getByText('No forecast has been run for this queue yet.')).toBeVisible()

  // Publish a fresh one, then withdraw it: the queue has no live forecast, the version stays.
  await runForecast(page, queue, target, 'to withdraw')
  await versions.getByRole('button', { name: /Publish to withdraw/ }).click()
  await expect(versions.getByText('published')).toBeVisible()
  await versions.getByRole('button', { name: /Archive to withdraw/ }).click()
  const archive = page.getByRole('form', { name: 'Archive to withdraw' })
  await expect(archive).toContainText('will have no published forecast')
  await archive.getByLabel(/Reason/).fill('e2e: bad import')
  await archive.getByRole('button', { name: /Confirm: archive/ }).click()
  await expect(versions.getByText('archived')).toBeVisible()
  await expect(versions.getByText('published')).toHaveCount(0)
  await expect(versions.getByRole('button', { name: /^View/ })).toHaveCount(1)
  await expect(versions.getByRole('button', { name: /Archive|Discard|Publish/ })).toHaveCount(0)
})

test('a lead cannot discard or archive, in the screen or in the API', async ({ page }) => {
  await signIn(page, 'lead')
  await page.getByRole('link', { name: 'Forecast' }).click()
  await expect(page.getByRole('button', { name: /^Discard/ })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /^Archive/ })).toHaveCount(0)

  // Hiding the buttons is cosmetic: the API refuses the lead too, with the CSRF token sent.
  const csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
  const unknown = '00000000-0000-4000-8000-000000000000'
  for (const action of ['discard', 'archive']) {
    const response = await page.request.post(`/api/v1/forecasting/versions/${unknown}/${action}`, {
      headers: { 'X-CSRFToken': csrf },
      data: { reason: 'e2e lead attempt' },
    })
    expect(response.status()).toBe(403)
  }
})
