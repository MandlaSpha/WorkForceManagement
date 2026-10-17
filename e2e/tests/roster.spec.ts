import { expect, test, type Page } from '@playwright/test'

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
 * Shifts, people, roster and the planner heatmap, against the real stack (SCH-01..05, ENG-01,
 * PLN-01).
 *
 * The same hand-worked queue as the forecast spec: 10 answered calls at 10:00 on each of two
 * Mondays, so the forecast for the Monday after needs 5 people to roster at 10:00 (3 on the
 * phone, 30% shrinkage) and none at any other half-hour of that day. The dates are the next three
 * Mondays so the week picker is one click away; the queue is made up for this run, so nothing
 * else can reach its history.
 *
 *   one person on a 09:00-17:30 shift  -> 10:00 is 1 - 5 = -4, gap 4
 *   two people                         -> 10:00 is 2 - 5 = -3, gap 3
 *   everywhere else the day has no calls, so 2 scheduled against 0 required is +2
 *   scheduled people x half-hours: 2 x 17 = 34; required 5
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

async function addEmployee(page: Page, empNo: string, name: string, queue: string): Promise<void> {
  const form = page.getByRole('form', { name: 'Add an employee' })
  await form.getByLabel('Employee number').fill(empNo)
  await form.getByLabel('Name', { exact: true }).fill(name)
  await form.getByLabel(queue).check()
  await form.getByRole('button', { name: 'Add employee' }).click()
  await expect(page.getByRole('table', { name: 'Employees' }).getByText(name)).toBeVisible()
}

async function csrf(page: Page): Promise<string> {
  return (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
}

test('shifts, people and a roster change the planner heatmap, and publishing locks it', async ({
  page,
}) => {
  test.setTimeout(180_000)
  const id = rand(1_000_000)
  const queue = `E2E Queue r${id}`
  const shift = `T${id}`
  const target = addDays(nextMonday(), 0)
  const people = [
    { empNo: `T${id}A`, name: `Pat Example ${id}` },
    { empNo: `T${id}B`, name: `Sam Example ${id}` },
  ]
  const cell = (slot: number) => page.getByTestId(`cell-${target}-${slot}`)

  await test.step('a planner imports two earlier Mondays, which creates the queue', async () => {
    await signIn(page, 'planner')
    await importDay(page, addDays(target, -14), queue)
    await importDay(page, addDays(target, -7), queue)
    await signOut(page)
  })

  await test.step('an admin adds a shift and confirms the queue assumptions', async () => {
    await signIn(page, 'admin')
    await page.getByRole('link', { name: 'Configure' }).click()
    await page.getByLabel('Code').fill(shift)
    await page.getByRole('button', { name: 'Add shift' }).click()
    await expect(page.getByRole('list', { name: 'Shifts' }).getByText(shift)).toBeVisible()

    await page.getByRole('tab', { name: 'Queues' }).click()
    const settings = page.getByRole('form', { name: `Staffing settings for ${queue}` })
    await expect(settings.getByText('Defaults, not confirmed')).toBeVisible()
    await settings.getByRole('button', { name: 'Confirm settings' }).click()
    await expect(settings.getByText('Confirmed', { exact: true })).toBeVisible()
    await signOut(page)
  })

  await test.step('a planner publishes a forecast for the target Monday', async () => {
    await signIn(page, 'planner')
    await page.getByRole('link', { name: 'Forecast' }).click()
    const form = page.getByRole('form', { name: 'Run a forecast' })
    await form.getByLabel('Queue').selectOption({ label: queue })
    await form.getByLabel('From').fill(target)
    await form.getByLabel('To').fill(target)
    await form.getByLabel('Label (optional)').fill('e2e roster')
    await form.getByRole('button', { name: 'Run forecast' }).click()
    await expect(page.getByTestId('max-required')).toHaveText('5')
    const versions = page.getByRole('table', { name: 'Versions' })
    await versions.getByRole('button', { name: /Publish e2e roster/ }).click()
    await expect(versions.getByText('published')).toBeVisible()
  })

  await test.step('the planner adds two people who can work the queue', async () => {
    await page.getByRole('link', { name: 'Employees' }).click()
    for (const p of people) {
      await page.getByRole('button', { name: 'Add employee' }).click()
      await addEmployee(page, p.empNo, p.name, queue)
    }
    // Hours nobody entered are shown as a default, not as a contract figure.
    const row = page.getByRole('row', { name: new RegExp(people[0]!.name) })
    await expect(row.getByText('Default')).toBeVisible()
  })

  await test.step('with nobody rostered the gap is the whole requirement', async () => {
    await page.getByRole('link', { name: 'Roster' }).click()
    await page.getByLabel('Queue').selectOption({ label: queue })
    await page.getByRole('button', { name: 'Next week' }).click()
    await page.getByRole('link', { name: 'Planner' }).click()
    await expect(cell(20)).toHaveText('−5')
    await expect(page.getByTestId('kpi-gap')).toContainText('0 scheduled · 5 required')
    await expect(page.getByTestId('kpi-worst')).toContainText('−5')
    await expect(page.getByTestId('assumptions-notice')).toHaveCount(0)
    // A day the forecast does not cover is unknown, never zero.
    await expect(page.getByTestId(`cell-${addDays(target, 1)}-20`)).toHaveText('·')
  })

  await test.step('each person rostered moves the heatmap straight away', async () => {
    await page.getByRole('link', { name: 'Roster' }).click()
    await page
      .getByLabel(new RegExp(`Shift for ${people[0]!.name} on Mon`))
      .selectOption({ label: shift })
    await expect(page.getByTestId(`on-${target}`)).toHaveText('1 on')
    await page.getByRole('link', { name: 'Planner' }).click()
    await expect(cell(20)).toHaveText('−4')
    await expect(cell(18)).toHaveText('+1')

    await page.getByRole('link', { name: 'Roster' }).click()
    await page
      .getByLabel(new RegExp(`Shift for ${people[1]!.name} on Mon`))
      .selectOption({ label: shift })
    await expect(page.getByTestId(`on-${target}`)).toHaveText('2 on')
    await page.getByRole('link', { name: 'Planner' }).click()
    await expect(cell(20)).toHaveText('−3')
    await expect(cell(18)).toHaveText('+2')
    await expect(page.getByTestId('kpi-gap')).toContainText('34 scheduled · 5 required')
    await expect(page.getByTestId('kpi-worst')).toContainText('−3 at 10:00')
    await expectNoAccessibilityViolations(page)
    // The under/over colours must keep their contrast in dark mode too.
    await page.getByRole('button', { name: 'Switch to dark mode' }).click()
    await expect(page.locator('html')).toHaveClass(/dark/)
    await expectNoAccessibilityViolations(page)
    await page.getByRole('button', { name: 'Switch to light mode' }).click()
  })

  await test.step('clearing a shift takes the person off the day again', async () => {
    await page.getByRole('link', { name: 'Roster' }).click()
    await page.getByLabel(new RegExp(`Shift for ${people[1]!.name} on Mon`)).selectOption('')
    await expect(page.getByTestId(`on-${target}`)).toHaveText('1 on')
  })

  await test.step('publishing locks the week in the screen and in the API', async () => {
    await page.getByRole('button', { name: 'Publish' }).click()
    await expect(page.getByTestId('roster-status')).toHaveText(/published/)
    await expect(page.getByLabel(new RegExp(`Shift for ${people[0]!.name} on Mon`))).toBeDisabled()

    const queues = await (await page.request.get('/api/v1/telephony/queues')).json()
    const employees = await (await page.request.get('/api/v1/scheduling/employees')).json()
    const response = await page.request.put('/api/v1/scheduling/roster/assignments', {
      headers: { 'X-CSRFToken': await csrf(page) },
      data: {
        queueId: queues.find((q: { name: string }) => q.name === queue).id,
        employeeId: employees.find((e: { name: string }) => e.name === people[1]!.name).id,
        day: target,
        templateId: null,
      },
    })
    expect(response.status()).toBe(409)
    expect((await response.json()).code).toBe('roster.published')
    await signOut(page)
  })

  await test.step('a lead reads the roster and the plan but cannot change either', async () => {
    await signIn(page, 'lead')
    await page.getByRole('link', { name: 'Roster' }).click()
    await page.getByLabel('Queue').selectOption({ label: queue })
    await page.getByRole('button', { name: 'Next week' }).click()
    await expect(page.getByLabel(new RegExp(`Shift for ${people[0]!.name} on Mon`))).toBeDisabled()
    await expect(page.getByRole('button', { name: 'Publish' })).toHaveCount(0)

    // Hiding the controls is cosmetic: the API refuses the lead as well.
    const response = await page.request.put('/api/v1/scheduling/roster/assignments', {
      headers: { 'X-CSRFToken': await csrf(page) },
      data: { queueId: 1, employeeId: 1, day: target, templateId: null },
    })
    expect(response.status()).toBe(403)
    const shifts = await page.request.post('/api/v1/scheduling/shifts', {
      headers: { 'X-CSRFToken': await csrf(page) },
      data: { code: 'NOPE', startTime: '09:00', endTime: '17:00', paidMinutes: 480 },
    })
    expect(shifts.status()).toBe(403)
  })
})

test('only an admin may open Configure, and an agent cannot open the roster or planner', async ({
  page,
}) => {
  await signIn(page, 'planner')
  await page.goto('/configure')
  await expect(
    page.getByRole('heading', { name: "You don't have access to this page" }),
  ).toBeVisible()
  await signOut(page)

  await signIn(page, 'agent')
  for (const path of ['/roster', '/planner', '/employees']) {
    await page.goto(path)
    await expect(
      page.getByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  }
})
