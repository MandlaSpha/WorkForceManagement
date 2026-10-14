import { expect, test, type Page } from '@playwright/test'

import { expectNoAccessibilityViolations, importDay, nextMonday, PASSWORD, signIn } from './helpers'
import { addDays, rand } from './report'

/**
 * The events calendar against the real stack (FC-04).
 *
 * The same hand-worked queue as the forecast spec: 10 answered calls at 10:00 on each of two
 * Mondays, handled in 180 s each, so the Monday after is forecast at 10 calls and needs 5 people
 * to roster (3 on the phone, 30% shrinkage).
 *
 * A planned payment run adding 100% doubles that to 20 calls at 10:00:
 *   traffic  20 / 1800 s * 180 s = 2 Erlangs
 *   3 agents do not reach 80% in 20 s, 4 do (about 86%)  -> 4 on the phone
 *   30% shrinkage: ceil(4 / 0.7) = ceil(5.71) = 6 to roster
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

async function runForecast(page: Page, queue: string, day: string, label: string): Promise<void> {
  const form = page.getByRole('form', { name: 'Run a forecast' })
  await form.getByLabel('Queue').selectOption({ label: queue })
  await form.getByLabel('Model').selectOption('baseline')
  await form.getByLabel('From').fill(day)
  await form.getByLabel('To').fill(day)
  await form.getByLabel('Label (optional)').fill(label)
  await form.getByRole('button', { name: 'Run forecast' }).click()
  await expect(page.getByRole('heading', { name: `${queue}: ${label}` })).toBeVisible()
}

test('an event adjusts the forecasts run after it, and removing it stops that', async ({
  page,
}) => {
  test.setTimeout(120_000)
  const id = rand(1_000_000)
  const queue = `E2E Queue e${id}`
  const eventName = `Payment run ${id}`
  const target = addDays(nextMonday(), 7)

  await signIn(page, 'planner')
  await importDay(page, addDays(target, -14), queue)
  await importDay(page, addDays(target, -7), queue)
  await page.getByRole('link', { name: 'Forecast' }).click()

  await runForecast(page, queue, target, 'before')
  await expect(page.getByTestId('total-calls')).toHaveText('10.0')
  await expect(page.getByTestId('max-required')).toHaveText('5')
  await expect(page.getByTestId('events-notice')).toHaveCount(0)

  // The planner adds the event for this queue only.
  const add = page.getByRole('form', { name: 'Add an event' })
  await add.getByLabel('Name').fill(eventName)
  await add.getByLabel('First day').fill(target)
  await add.getByLabel('Last day').fill(target)
  await add.getByLabel('Applies to').selectOption({ label: queue })
  await add.getByLabel('Change in calls (%)').fill('100')
  await add.getByRole('button', { name: 'Add event' }).click()
  const events = page.getByRole('table', { name: 'Events' })
  const row = events.getByRole('row', { name: new RegExp(eventName) })
  await expect(row).toContainText('+100%')
  await expect(row).toContainText(queue)

  // The forecast run before it is untouched; the one run after it is doubled and says why.
  await expect(page.getByTestId('total-calls')).toHaveText('10.0')
  await runForecast(page, queue, target, 'after')
  await expect(page.getByTestId('total-calls')).toHaveText('20.0')
  await expect(page.getByTestId('max-required')).toHaveText('6')
  await expect(page.getByTestId('events-notice')).toContainText(`${eventName} (+100%)`)
  await expectNoAccessibilityViolations(page)

  // Removing the event stops it adjusting new forecasts.
  await events.getByRole('button', { name: `Remove event ${eventName}` }).click()
  await expect(events.getByText(eventName)).toHaveCount(0)
  await runForecast(page, queue, target, 'removed')
  await expect(page.getByTestId('total-calls')).toHaveText('10.0')
  await expect(page.getByTestId('events-notice')).toHaveCount(0)
})

test('a lead reads the calendar but cannot change it, in the screen or in the API', async ({
  page,
}) => {
  await signIn(page, 'lead')
  await page.getByRole('link', { name: 'Forecast' }).click()
  await expect(page.getByRole('heading', { name: 'Events' })).toBeVisible()
  await expect(page.getByRole('form', { name: 'Add an event' })).toHaveCount(0)

  const csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
  const response = await page.request.post('/api/v1/forecasting/events', {
    headers: { 'X-CSRFToken': csrf },
    data: {
      name: 'Nope',
      queueId: null,
      dateFrom: '2026-12-01',
      dateTo: '2026-12-01',
      upliftPct: 10,
    },
  })
  expect(response.status()).toBe(403)
})
