import { expect, test } from '@playwright/test'

import { expectNoAccessibilityViolations, PASSWORD, signIn, signOut } from './helpers'
import { addDays, rand } from './report'

/**
 * Leave and approvals against the real stack (LV-01 to LV-03).
 *
 * The demo agent (a synthetic employee record) asks for unpaid leave, which has no limit, so runs
 * never use up a balance. The dates are two working days a random number of weeks ahead (a Monday
 * and the Tuesday after), so repeated runs do not overlap each other's requests. The lead sees
 * what it would do to coverage, approves it, and the agent then cancels it; the roster itself
 * (approval taking shifts off, cancelling putting them back) is covered with hand-worked numbers
 * by the API tests.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

/** A Monday between 8 and 90 weeks from now, as an ISO date, in a month with no public holiday
 * (February, July, October, November), so the Monday and the Tuesday after it are both working
 * days and the "2 working days" the spec expects does not depend on the calendar. */
function someMonday(): string {
  const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Africa/Johannesburg' })
  const day = new Date(`${today}T00:00:00Z`)
  const toMonday = (8 - day.getUTCDay()) % 7 || 7
  for (;;) {
    const monday = addDays(today, toMonday + 7 * (8 + rand(82)))
    if ([2, 7, 10, 11].includes(Number(monday.slice(5, 7)))) return monday
  }
}

test('an agent asks for leave, a lead sees its effect and approves it, and the agent can cancel it', async ({
  page,
}) => {
  test.setTimeout(120_000)
  const monday = someMonday()
  const tuesday = addDays(monday, 1)

  // The agent: balances, then asks.
  await signIn(page, 'agent')
  // Unpaid-leave requests an earlier run left waiting (it died before cancelling) would be found
  // first by the lead's list below: withdraw them, so this run sees only its own.
  const csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
  const stale = await (
    await page.request.get('/api/v1/people/leave/requests?status=pending')
  ).json()
  for (const old of stale.filter((r: { leaveType: string }) => r.leaveType === 'Unpaid leave')) {
    await page.request.post(`/api/v1/people/leave/requests/${old.id}/cancel`, {
      headers: { 'X-CSRFToken': csrf },
    })
  }
  await page.goto('/leave')
  await expect(page.getByTestId('balance-annual')).toContainText('days left')
  await expect(page.getByTestId('balance-unpaid')).toContainText('no limit')
  await expect(page.getByTestId('defaults-notice')).toBeVisible()
  await page.getByRole('button', { name: 'Request leave' }).click()
  const form = page.getByRole('form', { name: 'Ask for leave' })
  await form.getByLabel('Kind of leave').selectOption({ label: 'Unpaid leave' })
  await form.getByLabel('First day').fill(monday)
  await form.getByLabel('Last day').fill(tuesday)
  await page
    .getByRole('dialog', { name: 'Request leave' })
    .getByRole('button', { name: 'Ask for leave' })
    .click()
  await expect(page.getByTestId('apply-result')).toContainText('Asked for 2 working days')
  await expectNoAccessibilityViolations(page)
  await signOut(page)

  // The lead: the request is waiting, with its effect on coverage, and is approved.
  await signIn(page, 'lead')
  await page.goto('/leave')
  // The lead was told there is something to decide.
  await page.getByRole('button', { name: /^Notifications/ }).click()
  await expect(page.getByRole('region', { name: 'Notifications' })).toContainText(
    'Leave is waiting for your decision.',
  )
  await page.keyboard.press('Escape')
  // Leads open on the board: the request is a card under Pending, with its effect on coverage.
  const pending = page.getByTestId('kanban-col-pending')
  const request = pending
    .getByRole('listitem')
    .filter({ hasText: 'Alex Agent' })
    .filter({ hasText: 'Unpaid leave' })
    .first()
  await expect(request).toContainText('2 days')
  await expect(request.getByTestId('coverage-chip')).toContainText('No roster change') // not rostered
  // The same request is still on the list, with the full impact text.
  await page.getByRole('tab', { name: 'List', exact: true }).click()
  await page.getByRole('tab', { name: 'Approvals' }).click()
  await page
    .getByRole('button', { name: 'Show coverage impact for Alex Agent' })
    .first()
    .click()
  await expect(page.getByTestId('impact').first()).toContainText('nothing changes in the roster')
  await page.getByRole('tab', { name: 'Board', exact: true }).click()
  // Approve it by dragging the card onto Approved (the Move to menu does the same by keyboard).
  await request.dragTo(page.getByTestId('kanban-col-approved'))
  await expect(page.getByTestId('decision-result')).toContainText('Approved leave for Alex Agent')
  await signOut(page)

  // The agent: approved, and can still cancel it.
  await signIn(page, 'agent')
  await page.goto('/leave')
  // And the agent was told the outcome, without being told who decided.
  await page.getByRole('button', { name: /^Notifications/ }).click()
  await expect(page.getByRole('region', { name: 'Notifications' })).toContainText('was approved.')
  await page.keyboard.press('Escape')
  const mine = page.getByTestId('my-requests').getByRole('row').filter({ hasText: 'Unpaid leave' })
  const row = mine.filter({ hasText: 'Approved' }).first()
  await expect(row).toBeVisible()
  await row.getByRole('button', { name: /Cancel leave/ }).click()
  await expect(page.getByTestId('decision-result')).toContainText('Cancelled leave for Alex Agent')
})

test('an agent cannot decide leave and the others cannot read it, in the screen or in the API', async ({
  page,
}) => {
  await signIn(page, 'agent')
  await page.goto('/leave')
  await expect(page.getByRole('tab', { name: 'Approvals' })).toHaveCount(0)
  await expect(page.getByRole('tab', { name: 'Entitlements' })).toHaveCount(0)
  const csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
  const decide = await page.request.post('/api/v1/people/leave/requests/1/approve', {
    headers: { 'X-CSRFToken': csrf },
  })
  expect(decide.status()).toBe(403)
  const setLimit = await page.request.put('/api/v1/people/leave/types/1', {
    headers: { 'X-CSRFToken': csrf },
    data: { daysPerYear: 99 },
  })
  expect(setLimit.status()).toBe(403)
  await signOut(page)

  await signIn(page, 'executive')
  await page.goto('/leave')
  await expect(
    page.getByRole('heading', { name: "You don't have access to this page" }),
  ).toBeVisible()
  expect((await page.request.get('/api/v1/people/leave/requests')).status()).toBe(403)
})

test('an admin sets a blackout period, leave inside it is refused with the reason, and removing it lets it through', async ({
  page,
}) => {
  test.setTimeout(120_000)
  // Far enough ahead (about two years) not to touch any other spec's leave, which is under 90 weeks.
  const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Africa/Johannesburg' })
  // A random week, so a run that died before its clean-up cannot make every later run collide with it.
  const start = addDays(today, 600 + 7 * rand(14))
  const weekday = new Date(`${start}T00:00:00Z`).getUTCDay() // 0 is Sunday
  const wednesday = addDays(start, (3 - weekday + 7) % 7)
  const name = `E2E close ${rand(100_000)}`

  await signIn(page, 'admin')
  // Blackouts left by earlier runs that died before their clean-up would clutter every later run
  // and every real screen on this database: remove them first.
  const csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
  const left = await (await page.request.get('/api/v1/people/leave/blackouts')).json()
  for (const old of left.filter((b: { name: string }) => b.name.startsWith('E2E close '))) {
    await page.request.delete(`/api/v1/people/leave/blackouts/${old.id}`, {
      headers: { 'X-CSRFToken': csrf },
    })
  }
  await page.goto('/leave')
  await page.getByRole('tab', { name: 'Rules' }).click()
  const form = page.getByRole('form', { name: 'Add a blackout period' })
  await form.getByLabel(/^Name/).fill(name)
  await form.getByLabel('First day').fill(addDays(wednesday, -2))
  await form.getByLabel('Last day').fill(addDays(wednesday, 2))
  await form.getByRole('button', { name: 'Add blackout period' }).click()
  await expect(page.getByRole('list', { name: 'Blackout periods' })).toContainText(name)
  await expectNoAccessibilityViolations(page)
  await signOut(page)

  await signIn(page, 'agent')
  await page.goto('/leave')
  await expect(page.getByTestId('leave-rules-notice')).toContainText(name)
  await page.getByRole('button', { name: 'Request leave' }).click()
  const ask = page.getByRole('form', { name: 'Ask for leave' })
  await ask.getByLabel('Kind of leave').selectOption({ label: 'Unpaid leave' })
  await ask.getByLabel('First day').fill(wednesday)
  await ask.getByLabel('Last day').fill(wednesday)
  await page
    .getByRole('dialog', { name: 'Request leave' })
    .getByRole('button', { name: 'Ask for leave' })
    .click()
  await expect(page.getByTestId('apply-error')).toContainText(name)
  // Sick leave cannot wait, so a blackout never refuses it.
  await ask.getByLabel('Kind of leave').selectOption({ label: 'Sick leave' })
  await page
    .getByRole('dialog', { name: 'Request leave' })
    .getByRole('button', { name: 'Ask for leave' })
    .click()
  await expect(page.getByTestId('apply-result')).toContainText('Asked for 1 working day')
  await signOut(page)

  // Clean up: cancel the sick leave request and remove the blackout so nothing is left behind.
  await signIn(page, 'agent')
  await page.goto('/leave')
  await page
    .getByTestId('my-requests')
    .getByRole('row')
    .filter({ hasText: 'Sick leave' })
    .filter({ hasText: 'Waiting' })
    .first()
    .getByRole('button', { name: /Cancel leave/ })
    .click()
  await expect(page.getByTestId('decision-result')).toContainText('Cancelled leave')
  await signOut(page)
  await signIn(page, 'admin')
  await page.goto('/leave')
  await page.getByRole('tab', { name: 'Rules' }).click()
  await page.getByRole('button', { name: `Remove ${name}` }).click()
  await expect(page.getByRole('button', { name: `Remove ${name}` })).toHaveCount(0)
})

test('a lead cannot see or decide leave of someone outside their team, a planner can', async ({
  page,
}) => {
  const id = rand(1_000_000)
  const day = someMonday()

  // A planner adds a person with no manager and asks for leave on their behalf.
  await signIn(page, 'planner')
  let csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
  const headers = () => ({ 'X-CSRFToken': csrf })
  const created = await page.request.post('/api/v1/scheduling/employees', {
    headers: headers(),
    data: { empNo: `E2E-U${id}`, name: `E2E Unmanaged ${id}`, skills: [] },
  })
  expect(created.status()).toBe(201)
  const employeeId = (await created.json()).id
  const types = await (await page.request.get('/api/v1/people/leave/types')).json()
  const unpaid = types.find((t: { code: string }) => t.code === 'unpaid').id
  const asked = await page.request.post('/api/v1/people/leave/requests', {
    headers: headers(),
    // Monday to Friday: a single random Monday can be a public holiday, which has no working days.
    data: { leaveTypeId: unpaid, startDate: day, endDate: addDays(day, 4), employeeId },
  })
  expect(asked.status()).toBe(201)
  const requestId = (await asked.json()).id
  await signOut(page)

  // The demo lead manages the demo agent, not this person: it is not in their list, and a
  // decision is answered as if the request did not exist.
  await signIn(page, 'lead')
  csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
  const listed = await (await page.request.get('/api/v1/people/leave/requests')).json()
  expect(listed.some((r: { id: number }) => r.id === requestId)).toBe(false)
  const decide = await page.request.post(`/api/v1/people/leave/requests/${requestId}/approve`, {
    headers: headers(),
  })
  expect(decide.status()).toBe(404)
  await signOut(page)

  await signIn(page, 'planner')
  csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
  const approved = await page.request.post(`/api/v1/people/leave/requests/${requestId}/reject`, {
    headers: headers(),
  })
  expect(approved.status()).toBe(200)
})
