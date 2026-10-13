import { expect, test, type Page } from '@playwright/test'
import ExcelJS from 'exceljs'

import { PASSWORD, signIn } from './helpers'

/**
 * Importing call data and reading it back, against the real stack (requirements DAT-01..04, 10).
 *
 * Each run builds its own tiny report in a made-up month in the early 2000s, so it never mixes
 * with real data (the dashboard opens on the LATEST month, which stays the real one) and never
 * collides with an earlier run. The report is synthetic: fake queue, fake IDs, no people.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

const HEADERS = [
  'Call ID',
  'Phone Number',
  'Call Type',
  'Queue',
  'Agent',
  'Start Time',
  'Queue Time',
  'Agent Time',
  'Hangup Time',
  'Call Duration',
  'Agent Duration',
  'Queue Wait Time',
  'Call Status',
  'Hangup By',
  'Total Hold Duration',
  'Disposition Duration',
]

const hms = (seconds: number) =>
  [Math.floor(seconds / 3600), Math.floor((seconds % 3600) / 60), seconds % 60]
    .map((n) => String(n).padStart(2, '0'))
    .join(':')

interface Call {
  type: 'INBOUND' | 'OUTBOUND'
  status: 'Agent' | 'Abandoned' | 'Dial'
  wait: number
  talk: number
  wrap: number
}

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
  { type: 'INBOUND', status: 'Agent', wait: 5, talk: 100, wrap: 10 },
  { type: 'INBOUND', status: 'Agent', wait: 10, talk: 200, wrap: 10 },
  { type: 'INBOUND', status: 'Agent', wait: 25, talk: 150, wrap: 10 },
  { type: 'INBOUND', status: 'Agent', wait: 3, talk: 50, wrap: 10 },
  { type: 'INBOUND', status: 'Abandoned', wait: 30, talk: 0, wrap: 0 },
  { type: 'OUTBOUND', status: 'Dial', wait: 0, talk: 500, wrap: 500 },
]

async function buildReport(): Promise<{ buffer: Buffer; month: string }> {
  const year = 2001 + Math.floor(Math.random() * 18)
  const month = 1 + Math.floor(Math.random() * 12)
  const day = 1 + Math.floor(Math.random() * 27)
  const firstId = 9_000_000_000 + Math.floor(Math.random() * 900_000_000)
  const date = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`

  const book = new ExcelJS.Workbook()
  const sheet = book.addWorksheet('Call Record Report')
  sheet.addRow(HEADERS)
  CALLS.forEach((call, index) => {
    const clock = `${date} 10:${String(index * 5).padStart(2, '0')}:00`
    const answered = call.status === 'Agent'
    const row: Record<string, string | number | null> = {
      'Call ID': firstId + index,
      'Phone Number': '27000000000', // fake, and never stored
      'Call Type': call.type,
      Queue: 'E2E Queue',
      Agent: answered ? 'Test Person (Agent900)' : null,
      'Start Time': clock,
      'Queue Time': clock,
      'Agent Time': answered ? clock : '0000-00-00 00:00:00',
      'Hangup Time': clock,
      'Call Duration': hms(call.wait + call.talk),
      'Agent Duration': hms(call.talk),
      'Queue Wait Time': hms(call.wait),
      'Call Status': call.status,
      'Hangup By': 'USER',
      'Total Hold Duration': hms(0),
      'Disposition Duration': hms(call.wrap),
    }
    sheet.addRow(HEADERS.map((name) => row[name] ?? null))
  })
  return {
    buffer: Buffer.from(await book.xlsx.writeBuffer()),
    month: `${year}-${String(month).padStart(2, '0')}`,
  }
}

const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

async function chooseReport(page: Page, buffer: Buffer): Promise<void> {
  await page
    .getByLabel('Call detail report (.xlsx)')
    .setInputFiles({ name: 'e2e-report.xlsx', mimeType: XLSX, buffer })
}

test('a planner imports a report and sees the measured figures on the dashboard', async ({
  page,
}) => {
  const { buffer, month } = await buildReport()
  await signIn(page, 'planner')

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
  await expect(page.getByRole('rowheader', { name: /E2E Queue/ })).toContainText('Unconfirmed')
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
  const { buffer } = await buildReport()
  const csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
  const response = await page.request.post('/api/v1/telephony/imports', {
    headers: { 'X-CSRFToken': csrf },
    multipart: { file: { name: 'sneaky.xlsx', mimeType: XLSX, buffer } },
  })
  expect(response.status()).toBe(403)
})

test('a request without the CSRF token is refused even for a planner', async ({ page }) => {
  await signIn(page, 'planner')
  const { buffer } = await buildReport()
  const response = await page.request.post('/api/v1/telephony/imports', {
    multipart: { file: { name: 'forged.xlsx', mimeType: XLSX, buffer } },
  })
  expect(response.status()).toBe(403)
})
