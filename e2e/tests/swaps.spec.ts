import { expect, test, type Page } from '@playwright/test'

import { expectNoAccessibilityViolations, importDay, PASSWORD, signIn, signOut } from './helpers'
import { addDays, rand, randomMonday } from './report'

/**
 * Shift swaps against the real stack (SWP-01).
 *
 * The demo agent works an early shift on one day and the demo lead a late shift on another, both
 * on a queue made up for this run. The agent offers the swap, the lead (the colleague) accepts it
 * and a planner approves it, after which the roster really has the two shifts exchanged. The days
 * are 22 to 28 days ahead: past the demo data's rostered weeks and inside the four weeks a swap
 * can be asked for. The shifts and the queue are named for this run and the roster is cleared at
 * the end, so repeated runs do not meet each other's shifts.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

async function csrf(page: Page): Promise<string> {
  return (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
}

async function send(page: Page, method: 'POST' | 'PUT', path: string, data: unknown) {
  const headers = { 'X-CSRFToken': await csrf(page) }
  const response =
    method === 'POST'
      ? await page.request.post(path, { headers, data })
      : await page.request.put(path, { headers, data })
  expect(response.status(), `${method} ${path}: ${await response.text()}`).toBeLessThan(300)
  return response.json()
}

function today(): string {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Africa/Johannesburg' })
}

function mondayOf(day: string): string {
  const weekday = new Date(`${day}T00:00:00Z`).getUTCDay() // 0 is Sunday
  return addDays(day, -((weekday + 6) % 7))
}

test('an agent offers a swap, the colleague accepts, a planner approves, and the roster changes', async ({
  page,
}) => {
  test.setTimeout(180_000)
  const id = rand(10_000)
  const queueName = `E2E Queue swap${id}`
  const early = `E2EA${id}`
  const late = `E2EB${id}`
  const first = addDays(today(), 22 + rand(3))
  const second = addDays(today(), 25 + rand(4))
  const week = (day: string) =>
    `/api/v1/scheduling/roster?queue_id=${queueId}&week_start=${mondayOf(day)}`
  let queueId = 0
  let agentId = 0
  let leadId = 0
  let shifts: Record<string, number> = {}

  await test.step('an admin adds the two shifts (only admins may)', async () => {
    await signIn(page, 'admin')
    const a = await send(page, 'POST', '/api/v1/scheduling/shifts', {
      code: early,
      startTime: '07:00',
      endTime: '15:30',
      paidMinutes: 480,
    })
    const b = await send(page, 'POST', '/api/v1/scheduling/shifts', {
      code: late,
      startTime: '13:00',
      endTime: '22:00',
      paidMinutes: 480,
    })
    shifts = { [early]: a.id, [late]: b.id }
    await signOut(page)
  })

  await test.step('a planner makes a queue and puts the agent and lead on the roster', async () => {
    await signIn(page, 'planner')
    await importDay(page, randomMonday(1990, 10), queueName)
    const queues = await (await page.request.get('/api/v1/telephony/queues')).json()
    queueId = queues.find((q: { name: string }) => q.name === queueName).id

    const people = await (await page.request.get('/api/v1/scheduling/employees')).json()
    for (const [empNo, setId] of [
      ['DEMO-AGENT', (v: number) => (agentId = v)],
      ['DEMO-LEAD', (v: number) => (leadId = v)],
    ] as const) {
      const person = people.find((p: { empNo: string }) => p.empNo === empNo)
      expect(person, `${empNo} should exist: run seed_demo`).toBeTruthy()
      setId(person.id)
      await send(page, 'PUT', `/api/v1/scheduling/employees/${person.id}`, {
        empNo: person.empNo,
        name: person.name,
        contractType: person.contractType,
        workMode: person.workMode,
        weeklyHours: person.weeklyHours,
        skills: [
          ...person.skills.map((s: { queueId: number; level: number }) => ({
            queueId: s.queueId,
            level: s.level,
          })),
          { queueId, level: 1 },
        ],
      })
    }
    const assign = (employeeId: number, day: string, templateId: number | null) =>
      send(page, 'PUT', '/api/v1/scheduling/roster/assignments', {
        queueId,
        employeeId,
        day,
        templateId,
      })
    await assign(agentId, first, shifts[early])
    await assign(leadId, second, shifts[late])
    await signOut(page)
  })

  await test.step('the agent posts their early shift, without naming anybody', async () => {
    await signIn(page, 'agent')
    await page.goto('/shift-swaps')
    const form = page.getByRole('form', { name: 'Post a shift swap' })
    const mine = form.getByLabel(/swap away/)
    await mine.selectOption(await mine.locator('option', { hasText: early }).getAttribute('value'))
    await expectNoAccessibilityViolations(page)
    await form.getByRole('button', { name: 'Post swap request' }).click()
    await expect(page.getByTestId('offer-result')).toContainText('will not see your name')
    await signOut(page)
  })

  await test.step('the colleague sees the request without the poster’s name and takes it', async () => {
    await signIn(page, 'lead')
    await page.goto('/shift-swaps')
    await page.getByRole('tab', { name: 'Open requests' }).click()
    const card = page.getByRole('listitem').filter({ hasText: early }).first()
    await expect(card).toContainText('A colleague on')
    await expect(card).not.toContainText('Alex Agent')
    // The API says the same: the board carries no name or employee number.
    const board = await (await page.request.get('/api/v1/people/swaps/board')).text()
    expect(board).not.toContain('Alex Agent')
    expect(board).not.toContain('DEMO-AGENT')
    await card.getByRole('button', { name: new RegExp(`Take the ${early} request`) }).click()
    const take = page.getByRole('form', { name: new RegExp(`Take the ${early} request`) })
    const offered = take.getByLabel(/in return/)
    await expect(offered.locator('option', { hasText: late })).toHaveCount(1)
    await offered.selectOption(
      await offered.locator('option', { hasText: late }).getAttribute('value'),
    )
    await take.getByRole('button', { name: 'Take this swap' }).click()
    await expect(page.getByTestId('swap-result')).toContainText('A lead decides next')
    // The lead is one of the two people, so cannot approve it even though leads may approve.
    const all = await (await page.request.get('/api/v1/people/swaps')).json()
    const matched = all.find(
      (x: { fromShift: string; toShift: string; status: string }) =>
        x.fromShift === early && x.toShift === late && x.status === 'awaiting_approval',
    )
    const approve = await page.request.post(`/api/v1/people/swaps/${matched.id}/approve`, {
      headers: { 'X-CSRFToken': await csrf(page) },
    })
    expect(approve.status()).toBe(403)
    await signOut(page)
  })

  await test.step('a planner approves it and the roster has the two shifts exchanged', async () => {
    await signIn(page, 'planner')
    await page.goto('/shift-swaps')
    await page.getByRole('tab', { name: 'Approvals' }).click()
    const row = page
      .getByRole('listitem')
      .filter({ hasText: early })
      .filter({ hasText: late })
      .first()
    await row
      .getByRole('button', { name: /Approve the swap between Alex Agent and Lee Lead/ })
      .click()
    await expect(page.getByTestId('swap-result')).toContainText('exchanged on the roster')

    const cells = async (day: string) => {
      const roster = await (await page.request.get(week(day))).json()
      const code = (employeeId: number) =>
        roster.rows
          .find((r: { employeeId: number }) => r.employeeId === employeeId)
          ?.cells.find((c: { day: string }) => c.day === day)?.code ?? null
      return { agent: code(agentId), lead: code(leadId) }
    }
    // The agent now works the late shift on the second day, the lead the early shift on the first.
    expect((await cells(first)).agent).toBeNull()
    expect((await cells(first)).lead).toBe(early)
    expect((await cells(second)).agent).toBe(late)
    expect((await cells(second)).lead).toBeNull()

    for (const [employeeId, day] of [
      [leadId, first],
      [agentId, second],
    ] as const) {
      await send(page, 'PUT', '/api/v1/scheduling/roster/assignments', {
        queueId,
        employeeId,
        day,
        templateId: null,
      })
    }
    await signOut(page)
  })
})

test('an agent cannot approve a swap and an executive cannot see them', async ({ page }) => {
  await signIn(page, 'agent')
  await page.goto('/shift-swaps')
  await expect(page.getByRole('tab', { name: 'Approvals' })).toHaveCount(0)
  const approve = await page.request.post('/api/v1/people/swaps/1/approve', {
    headers: { 'X-CSRFToken': await csrf(page) },
  })
  expect(approve.status()).toBe(403)
  await signOut(page)

  await signIn(page, 'executive')
  await page.goto('/shift-swaps')
  await expect(
    page.getByRole('heading', { name: "You don't have access to this page" }),
  ).toBeVisible()
  expect((await page.request.get('/api/v1/people/swaps')).status()).toBe(403)
})
