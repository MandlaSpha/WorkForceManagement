import { expect, test } from '@playwright/test'

import { expectNoAccessibilityViolations, PASSWORD, signIn, signOut } from './helpers'

/**
 * The agent's own pages against the real stack (ESS-01, SCH-08): declared availability and "My
 * schedule". The demo agent clears their own windows first, so repeated runs do not meet each
 * other's (overlapping windows are refused), then declares one, sees it, and removes it again.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

test('an agent declares a time they cannot work, sees it, and removes it', async ({ page }) => {
  await signIn(page, 'agent')
  const csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
  const mine = await (await page.request.get('/api/v1/people/availability')).json()
  for (const w of mine) {
    await page.request.delete(`/api/v1/people/availability/${w.id}`, {
      headers: { 'X-CSRFToken': csrf },
    })
  }

  await page.goto('/my-availability')
  await expect(page.getByTestId('how-it-works')).toContainText('does not mean you are free')
  await expect(page.getByTestId('nothing-declared')).toBeVisible()

  const form = page.getByRole('form', { name: 'Declare availability' })
  await form.getByLabel('Day').selectOption({ label: 'Friday' })
  await form.getByLabel('From').fill('12:00')
  await form.getByLabel('To').fill('13:30')
  await form.getByRole('button', { name: 'Add' }).click()
  const friday = page.getByTestId('day-Friday')
  await expect(friday).toContainText('12:00-13:30')
  await expect(friday).toContainText('Cannot work')
  await expectNoAccessibilityViolations(page)

  // An overlapping window is refused with the reason, and nothing is added.
  await form.getByLabel('Day').selectOption({ label: 'Friday' })
  await form.getByLabel('From').fill('13:00')
  await form.getByLabel('To').fill('14:00')
  await form.getByRole('button', { name: 'Add' }).click()
  await expect(page.getByTestId('declare-error')).toContainText('overlaps')

  await page.getByRole('button', { name: 'Remove Friday 12:00-13:30' }).click()
  await expect(page.getByTestId('nothing-declared')).toBeVisible()
})

test('the agent sees their schedule, and others cannot open the agent pages', async ({ page }) => {
  await signIn(page, 'agent')
  await page.goto('/my-schedule')
  await expect(page.getByRole('heading', { name: 'My schedule' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Ask for leave' })).toBeVisible()
  await expectNoAccessibilityViolations(page)
  await signOut(page)

  await signIn(page, 'executive')
  expect((await page.request.get('/api/v1/people/my-schedule')).status()).toBe(403)
  expect((await page.request.get('/api/v1/people/availability')).status()).toBe(403)
})
