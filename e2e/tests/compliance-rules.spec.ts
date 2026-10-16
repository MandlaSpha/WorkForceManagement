import { expect, test } from '@playwright/test'

import { expectNoAccessibilityViolations, PASSWORD, signIn, signOut } from './helpers'
import { rand } from './report'

/**
 * Compliance rules against the real stack (CFG-06).
 *
 * The rules are made to start in the year 2100, so the version this run adds never touches any other
 * spec's roster (it applies to no day anyone plans). What the roster does with a rule is proved in
 * the API tests; here the screen and the permission are.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

test('an admin sets rules and is warned when they are looser than the statutory minimum, and a planner cannot', async ({
  page,
}) => {
  test.setTimeout(90_000)
  const day = `2100-${String(1 + rand(12)).padStart(2, '0')}-${String(1 + rand(28)).padStart(2, '0')}`

  await signIn(page, 'admin')
  await page.goto('/configure')
  await page.getByRole('tab', { name: 'Rules' }).click()
  const form = page.getByRole('form', { name: 'Compliance rules' })
  await expect(form.getByTestId('rules-in-force')).toBeVisible()
  await expectNoAccessibilityViolations(page)

  await form.getByLabel('Starts on').fill(day)
  await form.getByLabel('Rest between shifts (hours)').fill('9')
  await form.getByLabel('Most days in a row').fill('7')
  await form.getByRole('button', { name: 'Save rules' }).click()
  const warnings = form.getByTestId('rules-saved-warning')
  await expect(warnings).toHaveCount(2)
  await expect(warnings.first()).toContainText('below the statutory')
  await expect(form.getByRole('list', { name: 'Rule versions' })).toContainText(`From ${day}`)
  await signOut(page)

  // A planner can read the rules but the API refuses any change.
  await signIn(page, 'planner')
  const csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
  expect((await page.request.get('/api/v1/scheduling/compliance-rules')).status()).toBe(200)
  const refused = await page.request.put('/api/v1/scheduling/compliance-rules', {
    headers: { 'X-CSRFToken': csrf },
    data: { effectiveFrom: day, minRestHours: 1, maxConsecutiveDays: 14, maxWeeklyHours: null },
  })
  expect(refused.status()).toBe(403)
  await signOut(page)
})
