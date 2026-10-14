import { expect, test } from '@playwright/test'

import { expectNoAccessibilityViolations, PASSWORD, signIn } from './helpers'
import { addDays, buildReport, callsAt10, rand, randomFirstId, randomMonday, XLSX } from './report'

/**
 * Forecast tuning and its back-test against the real stack (RPT-07).
 *
 * A queue whose Mondays rise: 10, 20 and 30 calls at 10:00. The baseline forecasts each Monday
 * from the Mondays before it, newest counting more (weights 1, 0.7). By hand:
 *
 *   4 weeks, recency 0.7   2nd Monday 10 (actual 20), 3rd (20 + 0.7 * 10) / 1.7 = 15.88 (actual 30)
 *                          day totals 51.8% right, forecasts ran 48.2% low, suggest 1.93
 *   1 week                 2nd Monday 10, 3rd 20 -> 60.0% right, 40.0% low, suggest 1.67
 *   1 week with 1.67       forecasts 16.7 and 33.4 against 20 and 30 -> bias about zero
 */
/** A bias under one per cent, with or without a sign: "0.0% (balanced)" or "+0.2% (ran high)". */
const SMALL_BIAS = /^(0\.0% \(balanced\)|[+\u2212]0\.\d% \(ran (high|low)\))$/

test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

test('a planner back-tests a tuning, applies the suggestion and saves it', async ({ page }) => {
  test.setTimeout(120_000)
  const queue = `E2E Queue t${rand(1_000_000)}`
  const first = randomMonday()

  await signIn(page, 'planner')
  for (const [week, calls] of [
    [0, 10],
    [1, 20],
    [2, 30],
  ] as const) {
    const date = addDays(first, 7 * week)
    const buffer = await buildReport({
      date,
      firstId: randomFirstId(),
      calls: callsAt10(calls),
      queue,
    })
    await page.goto('/imports')
    await page
      .getByLabel('Call detail report (.xlsx)')
      .setInputFiles({ name: `${date}.xlsx`, mimeType: XLSX, buffer })
    await page.getByRole('button', { name: 'Import report' }).click()
    await expect(page.getByTestId('reconciles')).toBeVisible({ timeout: 20_000 })
  }

  await page.getByRole('link', { name: 'Calibration' }).click()
  await page.getByLabel('Queue').selectOption({ label: queue })
  await expect(page.getByTestId('tuning-state')).toContainText('Defaults')

  // The defaults, scored on the two Mondays that can be forecast.
  await expect(page.getByTestId('daily-current')).toHaveText('51.8%')
  await expect(page.getByTestId('bias-current')).toHaveText('\u221248.2% (ran low)')
  await expect(page.getByTestId('suggestion')).toContainText('multiplier of 1.93')

  // Looking back one week does better on rising demand.
  const weeks = page.getByLabel('Look back (weeks)')
  await weeks.fill('1')
  await page.getByRole('button', { name: 'Back-test these settings' }).click()
  await expect(page.getByTestId('daily-candidate')).toHaveText('60.0%')
  await expect(page.getByTestId('bias-candidate')).toHaveText('\u221240.0% (ran low)')
  await expect(page.getByTestId('daily-current')).toHaveText('51.8%') // the saved one, unchanged
  await expect(page.getByTestId('verdict')).toContainText('better')
  await expect(page.getByTestId('suggestion')).toContainText('multiplier of 1.67')
  await expectNoAccessibilityViolations(page)

  // Apply the suggestion: the bias is gone.
  await page.getByRole('button', { name: /Use 1\.67/ }).click()
  await expect(page.getByLabel('Contacts multiplier')).toHaveValue('1.67')
  // 16.7 and 33.4 against 20 and 30: 50.1 against 50, under 1% either way.
  await expect(page.getByTestId('bias-candidate')).toHaveText(SMALL_BIAS)

  // Save it: the queue now has its own tuning, and the back-test compares with it.
  await page.getByRole('button', { name: "Save as this queue's tuning" }).click()
  await expect(page.getByTestId('tuning-state')).toHaveText('Saved')
  await page.reload()
  await page.getByLabel('Queue').selectOption({ label: queue })
  await expect(page.getByLabel('Look back (weeks)')).toHaveValue('1')
  await expect(page.getByLabel('Contacts multiplier')).toHaveValue('1.67')
  await expect(page.getByTestId('bias-current')).toHaveText(SMALL_BIAS)
})

test('only planners and admins open Calibration, and a lead cannot save a tuning', async ({
  page,
}) => {
  await signIn(page, 'lead')
  await page.goto('/calibration')
  await expect(
    page.getByRole('heading', { name: "You don't have access to this page" }),
  ).toBeVisible()

  const csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
  const read = await page.request.get('/api/v1/forecasting/tuning?queue_id=999999')
  expect(read.status()).toBe(404) // a lead may read; there is just no such queue
  const write = await page.request.put('/api/v1/forecasting/tuning', {
    headers: { 'X-CSRFToken': csrf },
    data: { queueId: 1, weeks: 2, decay: 0.7, volumeMultiplier: 1, ahtMultiplier: 1 },
  })
  expect(write.status()).toBe(403)
})
