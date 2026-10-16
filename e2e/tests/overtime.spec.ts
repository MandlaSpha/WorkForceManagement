import { expect, test, type Page } from '@playwright/test'

import { expectNoAccessibilityViolations, PASSWORD, signIn, signOut } from './helpers'
import { addDays, rand } from './report'

/**
 * Overtime against the real stack (OT-01).
 *
 * A planner asks for two hours of overtime for a person made up for this run; an admin who has put
 * a salary on file approves it; the cost is worked out on the server at the rules in force (R17 332
 * a month over 40 contract hours is R100 an hour; x1.5 for two hours is R300.00). The salary is
 * never shown back, a lead sees no rands, and the roles that may not ask, decide or read pay are
 * refused by the API as well as the screen.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

async function csrf(page: Page): Promise<string> {
  return (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
}

/** The first Wednesday at least 60 days ahead and a random number of weeks beyond it, so repeated
 * runs do not meet each other's overtime, and so it is neither a Sunday nor a public holiday. */
function aWednesday(): string {
  const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Africa/Johannesburg' })
  const ahead = addDays(today, 60 + 7 * rand(30))
  const weekday = new Date(`${ahead}T00:00:00Z`).getUTCDay() // 0 is Sunday
  return addDays(ahead, (3 - weekday + 7) % 7)
}

test('overtime is asked for, approved and priced from the salary on file, which is never shown', async ({
  page,
}) => {
  test.setTimeout(120_000)
  const id = rand(1_000_000)
  const name = `Olly Overtime ${id}`
  const day = aWednesday()

  await signIn(page, 'planner')
  await page.getByRole('link', { name: 'Employees' }).click()
  await page.getByRole('button', { name: 'Add employee' }).click()
  const add = page.getByRole('form', { name: 'Add an employee' })
  await add.getByLabel('Employee number').fill(`O${id}`)
  await add.getByLabel('Name', { exact: true }).fill(name)
  await add.getByRole('button', { name: 'Add employee' }).click()
  await expect(page.getByRole('table', { name: 'Employees' }).getByText(name)).toBeVisible()
  await signOut(page)

  await signIn(page, 'admin')
  await page.getByRole('link', { name: 'Overtime' }).click()
  await page.getByRole('tab', { name: 'Pay' }).click()
  await expectNoAccessibilityViolations(page)
  const pay = page.getByRole('form', { name: `Pay for ${name}` })
  await pay.getByLabel(`Monthly salary for ${name} (R)`).fill('17332')
  await pay.getByRole('button', { name: 'Save pay' }).click()
  await expect(page.getByTestId(`pay-O${id}`)).toContainText('Salary on file')
  // The salary is never shown again: the box is empty and the figure appears nowhere on the page.
  await expect(pay.getByLabel(`Monthly salary for ${name} (R)`)).toHaveValue('')
  await expect(page.locator('body')).not.toContainText('17332')
  await expect(page.locator('body')).not.toContainText('17 332')
  await signOut(page)

  await signIn(page, 'planner')
  await page.getByRole('link', { name: 'Overtime' }).click()
  const ask = page.getByRole('form', { name: 'Ask for overtime' })
  await ask.getByLabel('Person').selectOption({ label: name })
  await ask.getByLabel('Day').fill(day)
  await ask.getByLabel('From').fill('18:00')
  await ask.getByLabel('To').fill('20:00')
  await ask.getByRole('button', { name: 'Ask for overtime' }).click()
  await expect(page.getByTestId('ask-result')).toBeVisible()
  const row = page.getByRole('row').filter({ hasText: name })
  await expect(row).toContainText('Waiting')
  await expect(row).toContainText('Weekday')
  await expect(row.getByTestId('cost')).toContainText(/R\s*300[.,]00/)
  await expectNoAccessibilityViolations(page)
  await signOut(page)

  // The admin decides it (nobody decides their own, and a planner is not the person it is for here,
  // but approval is the admin's step in this journey).
  await signIn(page, 'admin')
  await page.getByRole('link', { name: 'Overtime' }).click()
  await page
    .getByRole('row')
    .filter({ hasText: name })
    .getByRole('button', { name: /^Approve overtime for/ })
    .click()
  const approved = page.getByRole('row').filter({ hasText: name })
  await expect(approved).toContainText('Approved')
  await expect(approved.getByTestId('cost')).toContainText(/R\s*300[.,]00/)
  await signOut(page)

  // A lead sees none of it: not the person (outside their team), and never a rand figure.
  await signIn(page, 'lead')
  await page.getByRole('link', { name: 'Overtime' }).click()
  await expect(page.getByRole('row').filter({ hasText: name })).toHaveCount(0)
  await expect(page.getByTestId('cost')).toHaveCount(0)
  const token = await csrf(page)
  const outsider = await page.request.get('/api/v1/scheduling/employees')
  const employee = (await outsider.json()).find((e: { name: string }) => e.name === name)
  const asked = await page.request.post('/api/v1/overtime/requests', {
    headers: { 'X-CSRFToken': token },
    data: { employeeId: employee.id, day, startTime: '10:00', endTime: '11:00', reason: '' },
  })
  expect(asked.status()).toBe(404) // outside their team
  expect((await page.request.get('/api/v1/overtime/pay')).status()).toBe(403)
  await signOut(page)

  // A planner cannot read or set pay, and the list they see never carries a salary.
  await signIn(page, 'planner')
  expect((await page.request.get('/api/v1/overtime/pay')).status()).toBe(403)
  const tokenPlanner = await csrf(page)
  const setPay = await page.request.put(`/api/v1/overtime/pay/${employee.id}`, {
    headers: { 'X-CSRFToken': tokenPlanner },
    data: { monthlySalary: 1, ordinarilyWorksSundays: false, clear: false },
  })
  expect(setPay.status()).toBe(403)
  const listed = await (await page.request.get('/api/v1/overtime/requests')).text()
  expect(listed).not.toContain('17332')
  await signOut(page)

  // An agent cannot ask for overtime.
  await signIn(page, 'agent')
  const agentAsk = await page.request.post('/api/v1/overtime/requests', {
    headers: { 'X-CSRFToken': await csrf(page) },
    data: { employeeId: employee.id, day, startTime: '10:00', endTime: '11:00', reason: '' },
  })
  expect(agentAsk.status()).toBe(403)
})
