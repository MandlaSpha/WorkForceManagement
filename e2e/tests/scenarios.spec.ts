import { expect, test } from '@playwright/test'

import { expectNoAccessibilityViolations, importDay, nextMonday, PASSWORD, signIn } from './helpers'
import { addDays, rand } from './report'

/**
 * What-if scenarios against the real stack (RPT-06).
 *
 * The same hand-worked queue as the forecast spec: 10 calls at 10:00 on two Mondays, so the Monday
 * after is forecast at 10 calls and needs 5 people to roster (3 on the phone, 30% shrinkage).
 *
 *   calls +100%     20 calls, 2 Erlangs -> 4 on the phone -> ceil(4 / 0.7) = 6   (+1)
 *   shrinkage 0%    3 on the phone, nothing added          -> 3                  (-2)
 *   agent-hours     5 x half an hour = 2.5; with 6 it is 3.0
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

test('a planner asks what-if questions and the forecast itself stays as it was', async ({
  page,
}) => {
  test.setTimeout(120_000)
  const queue = `E2E Queue s${rand(1_000_000)}`
  const target = addDays(nextMonday(), 21)

  await signIn(page, 'planner')
  await importDay(page, addDays(target, -14), queue)
  await importDay(page, addDays(target, -7), queue)
  await page.getByRole('link', { name: 'Forecast' }).click()

  const run = page.getByRole('form', { name: 'Run a forecast' })
  await run.getByLabel('Queue').selectOption({ label: queue })
  await run.getByLabel('Model').selectOption('baseline')
  await run.getByLabel('From').fill(target)
  await run.getByLabel('To').fill(target)
  await run.getByLabel('Label (optional)').fill('e2e scenario')
  await run.getByRole('button', { name: 'Run forecast' }).click()
  await expect(page.getByTestId('total-calls')).toHaveText('10.0')
  await expect(page.getByTestId('max-required')).toHaveText('5')

  const what = page.getByRole('form', { name: 'What if' })
  const day = page.getByTestId(`scenario-${target}`)

  // Twice the calls need one more person, and one more half-hour of work.
  await what.getByLabel('Change in calls (%)').fill('100')
  await what.getByRole('button', { name: 'Show what changes' }).click()
  await expect(day.locator('[data-col="calls"]')).toContainText('10 to 20')
  await expect(day.locator('[data-col="peak"]')).toContainText('5 to 6')
  await expect(day.locator('[data-col="peak"]')).toContainText('(+1)')
  await expect(day.locator('[data-col="hours"]')).toContainText('2.5 to 3.0')

  // No shrinkage: only the 3 on the phone, with the minus sign a reader can hear.
  await what.getByLabel('Change in calls (%)').fill('0')
  await what.getByLabel(/^Shrinkage/).fill('0')
  await what.getByRole('button', { name: 'Show what changes' }).click()
  await expect(day.locator('[data-col="peak"]')).toContainText('5 to 3')
  await expect(day.locator('[data-col="peak"]')).toContainText('(−2)')
  await expect(page.getByTestId('scenario-assumptions')).toContainText('Shrinkage 30% to 0%')
  await expectNoAccessibilityViolations(page)

  // Asking changed nothing: the same single draft, with the same figures.
  await expect(page.getByTestId('total-calls')).toHaveText('10.0')
  await expect(page.getByTestId('max-required')).toHaveText('5')
  await expect(page.getByRole('table', { name: 'Versions' }).getByRole('row')).toHaveCount(2)

  // A change beyond the field's own limit is stopped by the browser before anything is sent; the
  // server's own refusal of such a request is covered by the API tests.
  const calls = what.getByLabel('Change in calls (%)')
  await calls.fill('900')
  expect(await calls.evaluate((el: HTMLInputElement) => el.validity.rangeOverflow)).toBe(true)
})

test('a lead may ask, but executives and agents cannot, in the API or the screen', async ({
  page,
}) => {
  await signIn(page, 'lead')
  await page.getByRole('link', { name: 'Forecast' }).click()
  const csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
  const noVersion = await page.request.post('/api/v1/forecasting/scenarios', {
    headers: { 'X-CSRFToken': csrf },
    data: { versionId: '00000000-0000-0000-0000-000000000000' },
  })
  expect(noVersion.status()).toBe(404) // allowed to ask; there is just no such forecast

  await page.getByRole('button', { name: 'Sign out' }).click()
  await signIn(page, 'executive')
  const csrf2 = (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
  const refused = await page.request.post('/api/v1/forecasting/scenarios', {
    headers: { 'X-CSRFToken': csrf2 },
    data: { versionId: '00000000-0000-0000-0000-000000000000' },
  })
  expect(refused.status()).toBe(403)
})
