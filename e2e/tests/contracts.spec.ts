import { expect, test } from '@playwright/test'

import { importDay, PASSWORD, signIn, signOut } from './helpers'
import { expectNoAccessibilityViolations } from './helpers'
import { rand, randomMonday } from './report'

/**
 * Customers and contracts against the real stack (ENG-05, CAP-04).
 *
 * An admin adds a customer and a contract that holds a queue made up for this run to a 91% promise.
 * The queue itself then carries that target (the staffing maths reads the queue), planners can read
 * the contract and see it is measured and modelled honestly, and only the admin can change it.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

test('an admin adds a contract that holds a queue to its promise, and everybody else can only read it', async ({
  page,
}) => {
  test.setTimeout(120_000)
  const id = rand(1_000_000)
  const queueName = `E2E Queue k${id}`
  const customer = `E2E Customer ${id}`

  await signIn(page, 'planner')
  await importDay(page, randomMonday(1990, 10), queueName)
  await signOut(page)

  await signIn(page, 'admin')
  await page.goto('/contracts')
  await expectNoAccessibilityViolations(page)
  await page.getByLabel('Customer name').fill(customer)
  await page.getByRole('button', { name: 'Add customer' }).click()
  await page.getByRole('button', { name: 'Add contract' }).click()
  const form = page.getByRole('form', { name: 'Add a contract' })
  await form.getByLabel('Customer').selectOption({ label: customer })
  await form.getByLabel('Contract name').fill('Gold')
  await form.getByLabel('Service level promised (%)').fill('91')
  await form.getByLabel('Within (seconds)').fill('30')
  await form.getByLabel(queueName).check()
  await form.getByRole('button', { name: 'Add contract' }).click()

  const row = page.getByRole('row').filter({ hasText: customer })
  await expect(row).toContainText('91% in 30 s')
  await expect(row).toContainText(queueName)
  // No calls in the last 28 days (the made-up queue's history is years old): a missing figure.
  await expect(row).toContainText('No calls in the last 28 days')
  await expect(row).toContainText('No forecast for this week')

  // The queue now carries the contract's target, so the staffing maths needs no change.
  const queues = await (await page.request.get('/api/v1/telephony/queues')).json()
  const queue = queues.find((q: { name: string }) => q.name === queueName)
  expect(queue.slTargetPct).toBe(91)
  expect(queue.slThresholdS).toBe(30)
  // It does not confirm the settings nobody checked (shrinkage, occupancy).
  expect(queue.settingsConfirmed).toBe(false)
  await signOut(page)

  // A planner reads it, and cannot change it.
  await signIn(page, 'planner')
  await page.goto('/contracts')
  await expect(page.getByRole('row').filter({ hasText: customer })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Add contract' })).toHaveCount(0)
  const csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
  const refused = await page.request.post('/api/v1/contracts/customers', {
    headers: { 'X-CSRFToken': csrf },
    data: { name: 'Sneaky' },
  })
  expect(refused.status()).toBe(403)
  await signOut(page)
})

test('an agent cannot open contracts, in the screen or in the API', async ({ page }) => {
  await signIn(page, 'agent')
  await page.goto('/contracts')
  await expect(
    page.getByRole('heading', { name: "You don't have access to this page" }),
  ).toBeVisible()
  expect((await page.request.get('/api/v1/contracts')).status()).toBe(403)
})
