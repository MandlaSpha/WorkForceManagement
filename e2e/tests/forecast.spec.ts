import { expect, test, type Page } from '@playwright/test'

import { expectNoAccessibilityViolations, PASSWORD, signIn } from './helpers'
import { addDays, buildReport, rand, randomFirstId, randomMonday, XLSX, type Call } from './report'

/**
 * Forecast and staffing requirement, against the real stack (requirements FC-01..03, FC-05,
 * ENG-01, ENG-02).
 *
 * Two Mondays a week apart, each with exactly 10 answered calls at 10:00, are imported into a
 * queue made up for this run (so nothing from another run or from real data can reach its
 * history). The forecast for the Monday after is then known by hand:
 *
 *   volume   10 calls at 10:00 (the same on both days, so the recency weights do not matter)
 *   traffic  10 / 1800 s * 180 s = 1 Erlang
 *   2 agents reach SL 70.2% (target 80% in 20 s), 3 reach 92.7%  -> 3 on the phone
 *   30% shrinkage: ceil(3 / 0.7) = ceil(4.29) = 5 to roster
 *   accuracy: the second Monday is forecast from the first, 10 against 10 -> 100%
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

const TEN_CALLS: Call[] = Array.from({ length: 10 }, (_, i) => ({
  type: 'INBOUND',
  status: 'Agent',
  clock: `10:0${i}:00`,
  wait: 0,
  talk: 150,
  wrap: 30, // 180 s handling
}))

async function importDay(page: Page, date: string, queue: string): Promise<void> {
  const buffer = await buildReport({
    date,
    firstId: randomFirstId(),
    calls: TEN_CALLS,
    queue,
  })
  await page.goto('/imports')
  await page
    .getByLabel('Call detail report (.xlsx)')
    .setInputFiles({ name: `${date}.xlsx`, mimeType: XLSX, buffer })
  await page.getByRole('button', { name: 'Import report' }).click()
  await expect(page.getByTestId('reconciles')).toBeVisible()
}

test('a planner forecasts a day, sees the staffing worked out by hand, and publishes it', async ({
  page,
}) => {
  const queue = `E2E Queue f${rand(1_000_000)}`
  const monday = randomMonday()
  const target = addDays(monday, 14)
  await signIn(page, 'planner')
  await importDay(page, monday, queue)
  await importDay(page, addDays(monday, 7), queue)

  await page.getByRole('link', { name: 'Forecast' }).click()
  await expect(page.getByRole('heading', { name: 'Forecast', exact: true })).toBeVisible()
  // The top bar has a queue picker too, so the fields are found inside the form.
  const form = page.getByRole('form', { name: 'Run a forecast' })
  await form.getByLabel('Queue').selectOption({ label: queue })
  await form.getByLabel('From').fill(target)
  await form.getByLabel('To').fill(target)
  await form.getByLabel('Label (optional)').fill('e2e forecast')
  await form.getByRole('button', { name: 'Run forecast' }).click()

  // The new draft opens, with the numbers worked out in the comment above.
  await expect(page.getByRole('heading', { name: `${queue}: e2e forecast` })).toBeVisible()
  await expect(page.getByTestId('total-calls')).toHaveText('10.0')
  await expect(page.getByTestId('peak')).toContainText('10:00')
  await expect(page.getByTestId('peak')).toContainText('10.0 calls')
  await expect(page.getByTestId('max-required')).toHaveText('5')
  await expect(page.getByTestId('evidence')).toContainText('2 most recent earlier days')

  // Honest about what the figures rest on: the staffing settings are still assumed defaults.
  await expect(page.getByTestId('assumptions-notice')).toContainText(
    'defaults that nobody has confirmed',
  )

  // The chart exists and is described, and the page passes the accessibility check.
  await expect(
    page.getByRole('img', { name: /Busiest half-hour 10:00 with 10.0 calls/ }),
  ).toBeVisible()
  await expectNoAccessibilityViolations(page)

  // Measured on the real calls just imported.
  await expect(page.getByTestId('accuracy-daily')).toContainText('100.0%')
  await expect(page.getByTestId('accuracy-interval')).toContainText('100.0%')
  await expect(page.getByTestId('accuracy-days')).toContainText('Over 1 past day')

  // Publish: the draft becomes the live forecast.
  const versions = page.getByRole('table', { name: 'Versions' })
  await expect(versions.getByText('draft')).toBeVisible()
  await versions.getByRole('button', { name: /Publish e2e forecast/ }).click()
  await expect(versions.getByText('published')).toBeVisible()
  await expect(versions.getByRole('button', { name: /Publish/ })).toHaveCount(0)
})

test('a lead may read forecasts but cannot run or publish, in the screen or in the API', async ({
  page,
}) => {
  await signIn(page, 'lead')
  await page.getByRole('link', { name: 'Forecast' }).click()
  await expect(page.getByText(/Planners and admins run and publish them/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Run forecast' })).toHaveCount(0)

  // Hiding the button is cosmetic: the API refuses the lead too, with the CSRF token sent.
  const csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
  const response = await page.request.post('/api/v1/forecasting/versions', {
    headers: { 'X-CSRFToken': csrf },
    data: { queueId: 1, dateFrom: '2026-05-25', dateTo: '2026-05-25' },
  })
  expect(response.status()).toBe(403)
})

test('an agent cannot open the forecast', async ({ page }) => {
  await signIn(page, 'agent')
  await page.goto('/forecast')
  await expect(
    page.getByRole('heading', { name: "You don't have access to this page" }),
  ).toBeVisible()
})
