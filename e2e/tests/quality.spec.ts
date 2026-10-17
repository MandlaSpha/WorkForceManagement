import { expect, test, type Page } from '@playwright/test'

import { expectNoAccessibilityViolations, PASSWORD, signIn, signOut } from './helpers'
import { rand } from './report'

/**
 * Quality results (QUA-01) and service metrics (KPI-01) against the real stack.
 *
 * The demo agent is given a unique ACD login for this run (the old logins are put back at the
 * end), a planner loads a small made-up file, and the agent then sees their own results while
 * customer operations and executives cannot reach the screen. Service metrics are checked from a
 * work-item file that carries the survey columns.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

async function csrf(page: Page): Promise<string> {
  return (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
}

const today = (): string => new Date().toLocaleDateString('en-CA', { timeZone: 'Africa/Johannesburg' })

test('a planner loads quality results; the agent sees their own, nobody else sees them', async ({
  page,
}) => {
  test.setTimeout(120_000)
  const login = `e2e-q${rand(1_000_000)}`

  await signIn(page, 'agent')
  const mine = await page.request.get('/api/v1/quality/mine')
  expect(mine.status(), 'the demo agent is on the employee list').toBe(200)
  const { employeeId } = await mine.json()
  await signOut(page)

  await signIn(page, 'planner')
  const employees = await (await page.request.get('/api/v1/scheduling/employees')).json()
  const agent = employees.find((e: { id: number }) => e.id === employeeId)
  const before: string[] = agent.agentLogins
  const token = await csrf(page)
  const put = (logins: string[]) =>
    page.request.put(`/api/v1/scheduling/employees/${employeeId}/agent-logins`, {
      headers: { 'X-CSRFToken': token },
      data: { logins },
    })
  expect((await put([...before, login])).status()).toBe(200)

  const csv = [
    'login,date,score,kind,ref,csat,coaching_due,comment',
    `${login},${today()},82.5,call,${login}a,4,${today()},rude-secret-comment`,
    `${login},${today()},not-a-number,call,${login}b,,,`,
    `nobody-${login},${today()},70,call,${login}c,,,`,
  ].join('\n')
  await page.goto('/quality')
  await page
    .getByLabel('Quality results (.csv or .xlsx)')
    .setInputFiles({ name: 'quality.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) })
  await page.getByRole('button', { name: 'Import results' }).click()
  const done = page.getByTestId('quality-done')
  await expect(done).toContainText('1 added')
  await expect(page.getByTestId('row-errors')).toContainText('Line 3')
  await expect(page.getByTestId('unmapped')).toContainText(`nobody-${login}`)
  await expect(page.getByTestId('ignored')).toContainText('comment')
  await expect(page.getByText('rude-secret-comment')).toHaveCount(0)
  await expectNoAccessibilityViolations(page)
  await signOut(page)

  // The agent sees their own result, and no team table.
  await signIn(page, 'agent')
  await page.getByRole('link', { name: 'Quality' }).click()
  await expect(page.getByTestId('mine-average')).toContainText('82.5%')
  await expect(page.getByTestId('team-table')).toHaveCount(0)
  expect((await page.request.get('/api/v1/quality/team')).status()).toBe(403)
  await signOut(page)

  // Executives and customer operations cannot reach it at all.
  for (const who of ['executive', 'customerops']) {
    await signIn(page, who)
    await page.goto('/quality')
    await expect(
      page.getByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
    expect((await page.request.get('/api/v1/quality/mine')).status()).toBe(403)
    await signOut(page)
  }

  // Put the demo agent's logins back.
  await signIn(page, 'planner')
  const restore = await page.request.put(
    `/api/v1/scheduling/employees/${employeeId}/agent-logins`,
    { headers: { 'X-CSRFToken': await csrf(page) }, data: { logins: before } },
  )
  expect(restore.status()).toBe(200)
})

test('service metrics show beside staffing and the cost is for pay roles only', async ({
  page,
}) => {
  test.setTimeout(120_000)
  const run = rand(1_000_000)
  const pool = `E2E KPI p${run}`
  const at = (n: number) => `${today()} 0${n}:00`
  const csv = [
    'ref,pool,opened,closed,effort_minutes,fcr,csat,nps',
    `K${run}A,${pool},${at(1)},${at(5)},60,yes,5,10`,
    `K${run}B,${pool},${at(1)},${at(7)},30,no,2,3`,
    `K${run}C,${pool},${at(1)},,,,,`,
  ].join('\n')

  await signIn(page, 'planner')
  await page.getByRole('link', { name: 'Service desk' }).click()
  await page.getByRole('tab', { name: 'Bring in work' }).click()
  await page
    .getByLabel('Work items (.csv)')
    .setInputFiles({ name: 'k.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) })
  await page.getByRole('button', { name: 'Import work items' }).click()
  await expect(page.getByTestId('work-import-result')).toContainText('3 added')

  await page.getByRole('tab', { name: 'Service metrics' }).click()
  const row = page.getByRole('row', { name: new RegExp(pool) })
  await expect(row.locator('[data-col="closed"]')).toHaveText('2')
  await expect(row.locator('[data-col="mttr"]')).toContainText('5.0 h')
  await expect(row.locator('[data-col="fcr"]')).toContainText('50.0%')
  await expect(row.locator('[data-col="csat"]')).toContainText('3.50')
  await expect(row.locator('[data-col="nps"]')).toContainText('0')
  await expect(row.locator('[data-col="backlog"]')).toHaveText('1')
  await expectNoAccessibilityViolations(page)
  await signOut(page)

  await signIn(page, 'customerops')
  await page.getByRole('link', { name: 'Service desk' }).click()
  await page.getByRole('tab', { name: 'Service metrics' }).click()
  await expect(page.getByTestId('metrics-how')).toContainText('planners and admins only')
  await expect(page.getByTestId('service-metrics')).not.toContainText(/R\d/)
  const report = await page.request.get(`/api/v1/service-kpis/report?month=${today().slice(0, 7)}-01`)
  expect((await report.json()).costVisible).toBe(false)
})
