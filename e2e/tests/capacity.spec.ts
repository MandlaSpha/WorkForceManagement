import { expect, test, type Page } from '@playwright/test'

import {
  expectNoAccessibilityViolations,
  importDay,
  nextMonday,
  PASSWORD,
  signIn,
  signOut,
  openSettingsPage,
} from './helpers'
import { addDays, rand } from './report'

/**
 * Capacity against the 100 permanent + 250 seasonal workforce, on the real stack (CAP-01).
 *
 * The same hand-worked queue as the forecast spec: 10 calls at 10:00 on two Mondays means the
 * Monday after needs 5 people at 10:00 (3 on the phone, 30% shrinkage). Capacity adds queues up at
 * each half-hour, and other specs leave published forecasts behind in the shared database, so
 * the test does not assume an empty day: it reads the day's figure first and checks that
 * publishing this queue's forecast adds exactly 5 to the agents needed at once, and that the
 * split into permanent, seasonal and overflow follows from that peak.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

// The target Monday is six weeks after the current one: beyond the four weeks the demo data
// forecasts (seed_demo_data), so the day checked for "nobody forecast" is really empty.
const WEEKS_AHEAD = 6

/** The figures of one day's row, or null for the dash that means "not forecast". */
async function readDay(page: Page, day: string) {
  const row = page.getByTestId(`day-${day}`)
  await expect(row).toBeVisible()
  const number = async (col: string): Promise<number | null> => {
    const text = (await row.locator(`[data-col="${col}"]`).innerText()).trim()
    return text === '—' ? null : Number(text)
  }
  return {
    peak: await number('peak'),
    permanent: await number('permanent'),
    seasonal: await number('seasonal'),
    overflow: await number('overflow'),
  }
}

/** Opens Capacity. The week chosen in the top bar is remembered, so it is moved only once. */
async function openCapacity(page: Page): Promise<void> {
  await page.getByRole('link', { name: 'Capacity' }).click()
  await expect(page.getByRole('heading', { name: 'Capacity', exact: true })).toBeVisible()
}

async function goToTargetWeek(page: Page): Promise<void> {
  for (let n = 0; n < WEEKS_AHEAD; n++)
    await page.getByRole('button', { name: 'Next week' }).click()
}

test('publishing a forecast adds its people to the day, split permanent first', async ({
  page,
}) => {
  test.setTimeout(120_000)
  const queue = `E2E Queue c${rand(1_000_000)}`
  const target = addDays(nextMonday(), 7 * (WEEKS_AHEAD - 1))

  await signIn(page, 'planner')
  await importDay(page, addDays(target, -14), queue)
  await importDay(page, addDays(target, -7), queue)

  await openCapacity(page)
  await goToTargetWeek(page)
  const before = await readDay(page, target)
  const base = before.peak ?? 0
  // Another day, read now, to show this test's publish leaves it alone. Whoever else has a forecast
  // there (a real queue's month, say) is part of the baseline, not an error.
  const otherDayBefore = await readDay(page, addDays(target, 3))

  // Run and publish this queue's forecast for the target Monday.
  await page.getByRole('link', { name: 'Forecast' }).click()
  const form = page.getByRole('form', { name: 'Run a forecast' })
  await form.getByLabel('Queue').selectOption({ label: queue })
  await form.getByLabel('Model').selectOption('baseline')
  await form.getByLabel('From').fill(target)
  await form.getByLabel('To').fill(target)
  await form.getByLabel('Label (optional)').fill('e2e capacity')
  await form.getByRole('button', { name: 'Run forecast' }).click()
  await expect(page.getByTestId('max-required')).toHaveText('5')
  const versions = page.getByRole('table', { name: 'Versions' })
  await versions.getByRole('button', { name: /Publish e2e capacity/ }).click()
  await expect(versions.getByText('published')).toBeVisible()

  await openCapacity(page)
  // This queue's 5 people join whatever else is forecast at 10:00 that day.
  await expect.poll(async () => (await readDay(page, target)).peak).toBe(base + 5)
  const after = await readDay(page, target)

  // And the split follows from the peak: permanent staff first, then seasonal, then overflow.
  const peak = after.peak ?? 0
  expect(after.permanent).toBe(Math.min(peak, 100))
  expect(after.seasonal).toBe(Math.min(Math.max(peak - 100, 0), 250))
  expect(after.overflow).toBe(Math.max(peak - 350, 0))
  expect((after.permanent ?? 0) + (after.seasonal ?? 0) + (after.overflow ?? 0)).toBe(peak)

  // A day this forecast does not cover is unchanged: a dash stays a dash, not a zero.
  expect(await readDay(page, addDays(target, 3))).toEqual(otherDayBefore)

  await expectNoAccessibilityViolations(page)
  await page.getByRole('button', { name: 'Switch to dark mode' }).click()
  await expect(page.locator('html')).toHaveClass(/dark/)
  await expectNoAccessibilityViolations(page)
  await page.getByRole('button', { name: 'Switch to light mode' }).click()
})

test('an admin confirms the workforce limits and everybody who reads capacity sees them', async ({
  page,
}) => {
  await signIn(page, 'admin')
  await openSettingsPage(page, 'Configure')
  await page.getByRole('tab', { name: 'Workforce' }).click()
  const form = page.getByRole('form', { name: 'Workforce limits' })
  await expect(form.getByLabel('Permanent staff')).toHaveValue(/^\d+$/)
  // Confirm the figures as they are (the tender's 100 and 250 unless an earlier run set them).
  await form.getByRole('button', { name: /(Confirm|Save) limits/ }).click()
  await expect(form.getByTestId('limits-state')).toHaveText('Confirmed')
  await signOut(page)

  await signIn(page, 'executive')
  await page.getByRole('link', { name: 'Capacity' }).click()
  await expect(page.getByRole('heading', { name: 'Capacity', exact: true })).toBeVisible()
  await expect(page.getByTestId('limits-notice')).toHaveCount(0) // confirmed
  await expect(page.getByTestId('kpi-permanent')).toContainText(/\d+/)
})

test('a lead cannot open capacity or set its limits, in the screen or in the API', async ({
  page,
}) => {
  await signIn(page, 'lead')
  await page.goto('/capacity')
  await expect(
    page.getByRole('heading', { name: "You don't have access to this page" }),
  ).toBeVisible()

  const csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
  const read = await page.request.get('/api/v1/capacity?week_start=2026-05-25&weeks=1')
  expect(read.status()).toBe(403)
  const write = await page.request.put('/api/v1/capacity/limits', {
    headers: { 'X-CSRFToken': csrf },
    data: { permanentLimit: 1, seasonalLimit: 1 },
  })
  expect(write.status()).toBe(403)
})
