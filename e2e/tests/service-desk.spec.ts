import { expect, test } from '@playwright/test'

import { expectNoAccessibilityViolations, PASSWORD, signIn, signOut } from './helpers'
import { rand } from './report'

/**
 * The service desk workload against the real stack (SD-01).
 *
 * Dates are relative to today, and the period asked for is 28 days: any 28 days hold exactly 20
 * working days, so the numbers do not depend on the weekday the test runs. One person does
 * 360 productive minutes x 20 days = 7200 minutes. The pool has, in minutes:
 *
 *   A  480 due in 2 days        in the period
 *   B  240 due yesterday        breached, still to be done
 *   C  600 due in 40 days       outside the period
 *   D  no estimate, due in 3    in the period, effort unknown
 *   E  120 no deadline          in the backlog only
 *   backlog 480 + 240 + 600 + 120 = 1440 (24h); due in the period 480 + 240 = 720 (12h)
 *
 *   Three closed items opened in the last 28 days with 1800, 1200 and 600 minutes: 3600 over 20
 *   working days is 180 a day, and 180 x 20 = 3600 (60h) arriving.
 *   required = (720 + 3600) / 7200 = 0.60 people, "at least" because D has no estimate
 *   with 480 productive minutes a day: 4320 / 9600 = 0.45
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

const day = (offset: number, time = '12:00'): string => {
  const d = new Date(Date.now() + offset * 86_400_000)
  const date = d.toLocaleDateString('en-CA', { timeZone: 'Africa/Johannesburg' })
  return `${date} ${time}`
}

function workItems(pool: string, run: number): string {
  const rows = [
    `E2E${run}A,${pool},P2,${day(-60)},${day(2)},480,,Pat Secret`,
    `E2E${run}B,${pool},P1,${day(-60)},${day(-1)},240,,Pat Secret`,
    `E2E${run}C,${pool},P3,${day(-60)},${day(40)},600,,Pat Secret`,
    `E2E${run}D,${pool},P2,${day(-60)},${day(3)},,,Pat Secret`,
    `E2E${run}E,${pool},P4,${day(-60)},,120,,Pat Secret`,
    `E2E${run}F,${pool},P3,${day(-10)},${day(-3)},1800,${day(-5)},Pat Secret`,
    `E2E${run}G,${pool},P3,${day(-12)},${day(-5)},1200,${day(-7)},Pat Secret`,
    `E2E${run}H,${pool},P3,${day(-14)},${day(-7)},600,${day(-9)},Pat Secret`,
    `E2E${run}I,${pool},P3,${day(-14)},${day(-7)},sixty,,Pat Secret`, // cannot be read
  ]
  return ['ref,pool,priority,opened,due,effort_minutes,closed,requester', ...rows].join('\n') + '\n'
}

test('a planner brings in work, sees the people it needs, and the productive time changes that', async ({
  page,
}) => {
  test.setTimeout(120_000)
  const run = rand(1_000_000)
  const pool = `E2E Pool p${run}`
  const csv = Buffer.from(workItems(pool, run), 'utf-8')

  await signIn(page, 'planner')
  await page.getByRole('link', { name: 'Service desk' }).click()
  await expect(page.getByTestId('not-erlang')).toContainText('This is not Erlang')

  // Bring the work in: eight items are kept, one row cannot be read, and the personal column is
  // neither read nor stored.
  await page.getByRole('tab', { name: 'Bring in work' }).click()
  await page
    .getByLabel('Work items (.csv)')
    .setInputFiles({ name: 'items.csv', mimeType: 'text/csv', buffer: csv })
  await page.getByRole('button', { name: 'Import work items' }).click()
  const result = page.getByTestId('work-import-result')
  await expect(result).toContainText('8 added, 0 updated, 0 already up to date')
  await expect(result).toContainText('1 with an effort that is not a whole number of minutes')
  await expect(page.getByTestId('ignored-columns')).toContainText('requester')
  await expect(page.getByText('Pat Secret')).toHaveCount(0)

  // The same export again changes nothing.
  await page.getByRole('button', { name: 'Import work items' }).click()
  await expect(result).toContainText('0 added, 0 updated, 8 already up to date')

  // The workload, over 28 days.
  await page.getByRole('tab', { name: 'Demand & capacity' }).click()
  await page.getByLabel('Period').selectOption({ label: 'Next 28 days' })
  const row = page.getByTestId('pool-table').getByRole('row', { name: new RegExp(pool) })
  await expect(row.locator('[data-col="backlog"]')).toHaveText('24h')
  await expect(row.locator('[data-col="due"]')).toHaveText('12h')
  await expect(row.locator('[data-col="arriving"]')).toHaveText('60h')
  await expect(row.locator('[data-col="fte"]')).toHaveText('at least 0.60')
  await expect(row.locator('[data-col="breached"]')).toHaveText('1')
  await expect(row).toContainText('1 with no estimate')
  await expect(row).toContainText('1 with no deadline')
  await expectNoAccessibilityViolations(page)

  // More productive time per day: fewer people.
  const minutes = row.getByLabel(`Productive minutes a day for ${pool}`)
  await minutes.fill('480')
  await row.getByRole('button', { name: 'Save' }).click()
  await expect(row.locator('[data-col="fte"]')).toHaveText('at least 0.45')
})

test('customer operations read the workload but cannot change it, in the screen or in the API', async ({
  page,
}) => {
  await signIn(page, 'customerops')
  await page.getByRole('link', { name: 'Service desk' }).click()
  await expect(page.getByTestId('not-erlang')).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Bring in work' })).toHaveCount(0)
  await expect(page.getByRole('form', { name: /Productive minutes for/ })).toHaveCount(0)

  const csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
  const refused = await page.request.post('/api/v1/service-desk/imports', {
    headers: { 'X-CSRFToken': csrf },
    multipart: {
      file: { name: 'x.csv', mimeType: 'text/csv', buffer: Buffer.from('ref,pool,opened\n') },
    },
  })
  expect(refused.status()).toBe(403)
  await signOut(page)

  await signIn(page, 'lead')
  await page.goto('/service-desk')
  await expect(
    page.getByRole('heading', { name: "You don't have access to this page" }),
  ).toBeVisible()
  const read = await page.request.get('/api/v1/service-desk/demand?as_of=2026-05-25&days=7')
  expect(read.status()).toBe(403)
})
