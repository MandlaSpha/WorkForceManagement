import { expect, test } from '@playwright/test'

import { expectNoAccessibilityViolations, PASSWORD, signIn, signOut } from './helpers'

/**
 * The Team screen against the real stack. Read-only: it writes nothing, so it leaves the demo data
 * as found and needs no clean-up. Written to be run with `just e2e`; not yet run.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

test('a planner sees the team grid, opens a person and gets the keyboard back', async ({
  page,
}) => {
  await signIn(page, 'planner')
  await page.goto('/team')
  await expect(page.getByRole('heading', { name: 'Team' })).toBeVisible()
  const cards = page.getByRole('list', { name: 'People on the team' }).getByRole('button')
  await expect(cards.first()).toBeVisible()
  await expect(page.getByTestId('summary')).toBeVisible()

  // The default order is employee number; a ranking is only ever something the viewer picks.
  const numbers = await cards.evaluateAll((els) =>
    els.map((el) => /Open this week/.test(el.getAttribute('aria-label') ?? '')),
  )
  expect(numbers.every(Boolean)).toBe(true)

  // No pay, and no wellbeing reason, anywhere on the grid.
  await expect(page.getByRole('main')).not.toContainText(/overtime|salary|\bR\s?\d/i)
  await expectNoAccessibilityViolations(page)

  await cards.first().focus()
  await page.keyboard.press('Enter')
  const drawer = page.getByRole('dialog')
  await expect(drawer).toBeVisible()
  await expect(drawer.getByRole('heading', { name: 'Shifts this week' })).toBeVisible()
  await expect(drawer.getByRole('button', { name: 'Close' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(drawer).toBeHidden()
  await expect(cards.first()).toBeFocused()

  await page.getByRole('tab', { name: 'Hours' }).click()
  await expect(page.getByRole('tab', { name: 'Hours' })).toHaveAttribute('aria-selected', 'true')
})

test('the team endpoint serves a lead, a planner and an admin, and nobody else', async ({
  page,
}) => {
  for (const [username, status] of [
    ['lead', 200],
    ['planner', 200],
    ['admin', 200],
    ['agent', 403],
    ['executive', 403],
    ['customer_ops', 403],
  ] as const) {
    await signIn(page, username)
    const response = await page.request.get('/api/v1/people/team-overview')
    expect(response.status(), username).toBe(status)
    if (status === 200) {
      // Pay never travels with a team card.
      expect(JSON.stringify(await response.json())).not.toMatch(/rate|salary|overtime|cost/i)
    }
    await signOut(page)
  }
})

test('a lead naming a team that is not theirs gets a 404, not a 403', async ({ page }) => {
  await signIn(page, 'planner')
  const body = await (await page.request.get('/api/v1/people/team-overview')).json()
  const other = body.managers[0]
  await signOut(page)
  test.skip(!other, 'the demo data has no manager to name')

  await signIn(page, 'lead')
  const own = await (await page.request.get('/api/v1/people/team-overview')).json()
  // A lead's own screen offers no team filter; a manager id that is not theirs is simply not found.
  expect(own.managers).toEqual([])
  const response = await page.request.get(`/api/v1/people/team-overview?manager_id=999999999`)
  expect(response.status()).toBe(404)
})

test('a lead does not see the team filter and is not offered other teams', async ({ page }) => {
  await signIn(page, 'lead')
  await page.goto('/team')
  await expect(page.getByRole('heading', { name: 'Team' })).toBeVisible()
  await expect(page.getByLabel('Team', { exact: true })).toHaveCount(0)
})
