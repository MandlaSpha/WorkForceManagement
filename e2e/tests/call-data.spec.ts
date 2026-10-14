import { expect, test, type Page } from '@playwright/test'

import { PASSWORD, signIn } from './helpers'
import { buildReport, randomFirstId, randomMonday, XLSX, type Call } from './report'

/**
 * Importing call data and reading it back, against the real stack (requirements DAT-01..04, 10).
 *
 * Each run builds its own tiny report on a made-up day in the early 2000s, so it never mixes with
 * real data (the dashboard opens on the LATEST month, which stays the real one) and never collides
 * with an earlier run. The report is synthetic: fake queue, fake IDs, no people.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

/**
 * Inbound: four answered (waits 5, 10, 25, 3 s; handling 110, 210, 160, 60 s) and one abandoned.
 * One outbound call that must change no figure.
 *
 *   offered 5, answered 4, abandoned 1  -> abandon 20.00%
 *   within 20 s: 5, 10, 3 = 3 of 5      -> service level 60.0%
 *   ASA (5+10+25+3)/4 = 10.75           -> 10.8 s
 *   AHT (110+210+160+60)/4 = 135 s      -> 2:15
 */
const CALLS: Call[] = [
  { type: 'INBOUND', status: 'Agent', clock: '10:00:00', wait: 5, talk: 100, wrap: 10 },
  { type: 'INBOUND', status: 'Agent', clock: '10:05:00', wait: 10, talk: 200, wrap: 10 },
  { type: 'INBOUND', status: 'Agent', clock: '10:10:00', wait: 25, talk: 150, wrap: 10 },
  { type: 'INBOUND', status: 'Agent', clock: '10:15:00', wait: 3, talk: 50, wrap: 10 },
  { type: 'INBOUND', status: 'Abandoned', clock: '10:20:00', wait: 30, talk: 0, wrap: 0 },
  { type: 'OUTBOUND', status: 'Dial', clock: '10:25:00', wait: 0, talk: 500, wrap: 500 },
]

/** A report on a made-up Monday in a month that has no call data yet. The dashboard sums every
 * queue in a month, so a month an earlier run or another spec already used would add its calls to
 * the figures asserted here. */
async function report(page?: Page): Promise<{ buffer: Buffer; month: string }> {
  // Only the test that reads the figures back needs a month of its own; the refusal tests do not.
  const response = await page?.request.get('/api/v1/telephony/months')
  const used = new Set<string>(
    response ? ((await response.json()) as { months: string[] }).months : [],
  )
  // The 1990s: no other spec imports there, so none can add calls to this month while it runs.
  let date = randomMonday(1990, 10)
  for (let attempt = 0; attempt < 200 && used.has(date.slice(0, 7)); attempt++) {
    date = randomMonday(1990, 10)
  }
  const buffer = await buildReport({
    date,
    firstId: randomFirstId(),
    calls: CALLS,
    queue: 'E2E Queue',
  })
  return { buffer, month: date.slice(0, 7) }
}

async function chooseReport(page: Page, buffer: Buffer): Promise<void> {
  await page
    .getByLabel('Call detail report (.xlsx)')
    .setInputFiles({ name: 'e2e-report.xlsx', mimeType: XLSX, buffer })
}

test('a planner imports a report and sees the measured figures on the dashboard', async ({
  page,
}) => {
  await signIn(page, 'planner')
  const { buffer, month } = await report(page)

  await page.getByRole('link', { name: 'Data import' }).click()
  await expect(page.getByRole('heading', { name: 'Data import' })).toBeVisible()
  await chooseReport(page, buffer)
  await page.getByRole('button', { name: 'Import report' }).click()

  // The report reconciles, and says exactly what it did with the six rows.
  await expect(page.getByTestId('reconciles')).toBeVisible()
  await expect(page.getByText('Calls added').locator('xpath=following-sibling::dd')).toHaveText('6')
  await expect(page.getByRole('table').getByText('e2e-report.xlsx').first()).toBeVisible()

  // The same file again is refused, plainly, and nothing is added.
  await chooseReport(page, buffer)
  await page.getByRole('button', { name: 'Import report' }).click()
  await expect(page.getByTestId('import-error')).toContainText('imported before')
  await expect(page.getByTestId('reconciles')).toHaveCount(0)

  // The dashboard shows the figures worked out by hand in CALLS above.
  await page.getByRole('link', { name: 'Dashboard' }).click()
  await page.getByLabel('Month').selectOption(month)
  await expect(page.getByTestId('tile-offered')).toContainText('5')
  await expect(page.getByTestId('tile-abandon')).toContainText('20.00%')
  await expect(page.getByTestId('tile-sl')).toContainText('60.0%')
  await expect(page.getByTestId('tile-asa')).toContainText('10.8 s')
  await expect(page.getByTestId('tile-aht')).toContainText('2:15')
  await expect(page.getByTestId('coverage')).toContainText('of')
  await expect(
    page.getByRole('rowheader', { name: 'E2E Queue Unconfirmed', exact: true }),
  ).toContainText('Unconfirmed')
})

test('only planners and admins can reach the import, in the screen and in the API', async ({
  page,
}) => {
  await signIn(page, 'lead')
  await expect(page.getByRole('link', { name: 'Data import' })).toHaveCount(0)

  await page.goto('/imports')
  await expect(
    page.getByRole('heading', { name: "You don't have access to this page" }),
  ).toBeVisible()

  // Hiding the link is cosmetic. Calling the API directly, with a real file and the CSRF token a
  // browser would send, is still refused.
  const { buffer } = await report()
  const csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
  const response = await page.request.post('/api/v1/telephony/imports', {
    headers: { 'X-CSRFToken': csrf },
    multipart: { file: { name: 'sneaky.xlsx', mimeType: XLSX, buffer } },
  })
  expect(response.status()).toBe(403)
})

test('a request without the CSRF token is refused even for a planner', async ({ page }) => {
  await signIn(page, 'planner')
  const { buffer } = await report()
  const response = await page.request.post('/api/v1/telephony/imports', {
    multipart: { file: { name: 'forged.xlsx', mimeType: XLSX, buffer } },
  })
  expect(response.status()).toBe(403)
})
