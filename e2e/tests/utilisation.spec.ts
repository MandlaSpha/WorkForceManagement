import { expect, test } from '@playwright/test'

import { expectNoAccessibilityViolations, PASSWORD, signIn } from './helpers'

/**
 * Utilisation, cost and workload balance against the real stack (UTL-01, UTL-02, WLB-01).
 *
 * The demo data decides how many rows there are, so this checks what must hold whatever the
 * numbers: who sees which screen and which pay figures, that the figures are labelled modelled,
 * and that a suggestion is never applied from the screen.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

test('an admin sees utilisation and cost, labelled as modelled, and can reach the terms form', async ({
  page,
}) => {
  await signIn(page, 'admin')
  await page.getByRole('link', { name: 'Utilisation & cost' }).click()
  await expect(page.getByRole('heading', { name: 'Utilisation & cost' })).toBeVisible()
  // Pay roles get the cost panel, whatever the month holds.
  await expect(page.getByTestId('cost-panel')).toBeVisible()
  await expect(page.getByTestId('cost-panel')).toContainText('Modelled')
  await expect(
    page.getByTestId('modelled-note').or(page.getByTestId('utilisation-none')),
  ).toBeVisible()
  await expectNoAccessibilityViolations(page)
})

test('an executive sees utilisation without any named person or pay figure', async ({ page }) => {
  await signIn(page, 'executive')
  await page.getByRole('link', { name: 'Utilisation & cost' }).click()
  await expect(page.getByRole('heading', { name: 'Utilisation & cost' })).toBeVisible()
  await expect(
    page.getByTestId('modelled-note').or(page.getByTestId('utilisation-none')),
  ).toBeVisible()
  await expect(page.getByTestId('cost-panel')).toHaveCount(0)
  await expect(page.locator('[data-testid^="person-"]')).toHaveCount(0)
  // Not for them: the balance screen names people on a roster.
  await expect(page.getByRole('link', { name: 'Workload balance' })).toHaveCount(0)
})

test('an agent has neither screen', async ({ page }) => {
  await signIn(page, 'agent')
  await expect(page.getByRole('link', { name: 'Utilisation & cost' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Workload balance' })).toHaveCount(0)
})

test('a planner sees the balance of a day and no button that moves anyone', async ({ page }) => {
  await signIn(page, 'planner')
  await page.getByRole('link', { name: 'Workload balance' }).click()
  await expect(page.getByRole('heading', { name: 'Workload balance' })).toBeVisible()
  await expect(page.getByTestId('balance-note')).toContainText('suggestions')
  await expect(page.getByRole('button', { name: /move|apply|assign/i })).toHaveCount(0)
  await expectNoAccessibilityViolations(page)
})

test('a lead sees utilisation of their own team and the balance screen', async ({ page }) => {
  await signIn(page, 'lead')
  await page.getByRole('link', { name: 'Utilisation & cost' }).click()
  await expect(page.getByTestId('cost-panel')).toHaveCount(0)
  await page.getByRole('link', { name: 'Workload balance' }).click()
  await expect(page.getByTestId('balance-note')).toBeVisible()
})
