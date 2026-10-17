import { expect, test, type Page } from '@playwright/test'

import { importDay, nextMonday, PASSWORD, signIn, signOut } from './helpers'
import { addDays, rand } from './report'

/**
 * Recommendations against the real stack (REC-01).
 *
 * The same hand-worked queue as the roster spec: 10 answered calls at 10:00 on each of two Mondays
 * make the forecast for the Monday after need 5 people at 10:00 and none at any other half-hour.
 * Two people can work the queue, so two suggestions are on offer, one person each, and each closes one
 * half-hour. Applying one recalculates the list at once; after both nothing is left to suggest.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

async function csrf(page: Page): Promise<string> {
  return (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
}

test('a planner applies suggestions one at a time and the list recalculates, and a lead cannot', async ({
  page,
}) => {
  test.setTimeout(180_000)
  const id = rand(1_000_000)
  const queue = `E2E Queue c${id}`
  const shift = `C${id}`
  const target = nextMonday()
  const people = [`Pat Suggest ${id}`, `Sam Suggest ${id}`]

  await signIn(page, 'planner')
  await importDay(page, addDays(target, -14), queue)
  await importDay(page, addDays(target, -7), queue)
  await signOut(page)

  await signIn(page, 'admin')
  await page.getByRole('link', { name: 'Configure' }).click()
  // A half-hour shift at the peak, so one person covers exactly the 10:00 the forecast needs. A
  // whole-day shift would add more people than the half-hour is worth, and the optimiser rightly
  // declines (a half-hour short weighs three times a half-hour over, not seventeen).
  await page.getByLabel('Code').fill(shift)
  await page.getByLabel('Start').fill('10:00')
  await page.getByLabel('End').fill('10:30')
  await page.getByLabel('Paid minutes').fill('30')
  await page.getByRole('button', { name: 'Add shift' }).click()
  await expect(page.getByRole('list', { name: 'Shifts' }).getByText(shift)).toBeVisible()
  await page.getByRole('tab', { name: 'Queues' }).click()
  const settings = page.getByRole('form', { name: `Staffing settings for ${queue}` })
  await settings.getByRole('button', { name: 'Confirm settings' }).click()
  await expect(settings.getByText('Confirmed', { exact: true })).toBeVisible()
  await signOut(page)

  await signIn(page, 'planner')
  await page.getByRole('link', { name: 'Forecast' }).click()
  const form = page.getByRole('form', { name: 'Run a forecast' })
  await form.getByLabel('Queue').selectOption({ label: queue })
  await form.getByLabel('From').fill(target)
  await form.getByLabel('To').fill(target)
  await form.getByLabel('Label (optional)').fill('e2e auto')
  await form.getByRole('button', { name: 'Run forecast' }).click()
  await expect(page.getByTestId('max-required')).toHaveText('5')
  const versions = page.getByRole('table', { name: 'Versions' })
  await versions.getByRole('button', { name: /Publish e2e auto/ }).click()
  await expect(versions.getByText('published')).toBeVisible()

  await page.getByRole('link', { name: 'Employees' }).click()
  for (const [n, name] of people.entries()) {
    await page.getByRole('button', { name: 'Add employee' }).click()
    const add = page.getByRole('form', { name: 'Add an employee' })
    await add.getByLabel('Employee number').fill(`C${id}${n}`)
    await add.getByLabel('Name', { exact: true }).fill(name)
    await add.getByLabel(queue).check()
    await add.getByRole('button', { name: 'Add employee' }).click()
    await expect(page.getByRole('table', { name: 'Employees' }).getByText(name)).toBeVisible()
  }

  // The queue and week pickers appear only on screens that read them.
  await page.getByRole('link', { name: 'Roster' }).click()
  await page.getByLabel('Queue').selectOption({ label: queue })
  await page.getByRole('button', { name: 'Next week' }).click()

  await page.getByRole('link', { name: 'Recommendations' }).click()
  await expect(page.getByTestId('rec-gap')).toContainText('5')
  const list = page.getByRole('list', { name: 'Recommendations' })
  // Other specs' made-up shifts of the same shape are suggestions too, so count only a minimum.
  await expect(list.getByRole('listitem').nth(1)).toBeVisible()
  await expect(list.getByRole('listitem').first()).toContainText('closes 1 half-hours short')

  // Apply one: the gap and the list recalculate straight away.
  await list.getByRole('listitem').first().getByRole('button', { name: 'Apply' }).click()
  await expect(page.getByTestId('rec-gap')).toContainText('4')
  await expect(list.getByRole('listitem').first()).toBeVisible()
  await list.getByRole('listitem').first().getByRole('button', { name: 'Apply' }).click()
  await expect(page.getByTestId('rec-gap')).toContainText('3')
  await expect(page.getByTestId('rec-none')).toBeVisible()
  await page.getByRole('link', { name: 'Roster' }).click()
  await expect(page.getByTestId(`on-${target}`)).toHaveText('2 on')
  await signOut(page)

  // A lead cannot open the screen, and the API refuses them too.
  await signIn(page, 'lead')
  await page.goto('/recommendations')
  await expect(
    page.getByRole('heading', { name: "You don't have access to this page" }),
  ).toBeVisible()
  const refused = await page.request.post('/api/v1/scheduling/recommendations/apply', {
    headers: { 'X-CSRFToken': await csrf(page) },
    data: { queueId: 1, weekStart: target, employeeId: 1, day: target, templateId: 1 },
  })
  expect(refused.status()).toBe(403)
})
