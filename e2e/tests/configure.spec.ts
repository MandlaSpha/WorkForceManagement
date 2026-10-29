import { expect, test } from '@playwright/test'

import { expectNoAccessibilityViolations, PASSWORD, signIn } from './helpers'
import { rand } from './report'

/**
 * The Configure screen's shift library (the settings-card redesign): search, delete with a
 * confirmation step, and the segmented tabs. The shift this makes is named "E2E<digits>", which
 * the dev purge (purge_e2e_data) recognises and removes after the run.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

test('an admin adds a shift, finds it by search, and deletes it only after confirming', async ({
  page,
}) => {
  test.setTimeout(90_000)
  const code = `E2E${rand(1_000_000)}`

  await signIn(page, 'admin')
  await page.goto('/configure')
  await expect(page.getByRole('tablist', { name: 'Configuration' })).toBeVisible()
  await expectNoAccessibilityViolations(page)

  await page.getByLabel('Code').fill(code)
  await page.getByRole('button', { name: 'Add shift' }).click()

  await page.getByLabel('Search shifts').fill(code)
  const table = page.getByRole('table', { name: 'Shifts' })
  await expect(table.getByRole('rowheader', { name: code })).toBeVisible()

  // The first click only asks; Cancel leaves the shift where it is.
  await page.getByRole('button', { name: `Delete shift ${code}` }).click()
  await expect(page.getByText(`Delete ${code}?`)).toBeVisible()
  await page.getByRole('button', { name: 'Cancel' }).click()
  await expect(table.getByRole('rowheader', { name: code })).toBeVisible()

  await page.getByRole('button', { name: `Delete shift ${code}` }).click()
  await page.getByRole('button', { name: 'Yes, delete' }).click()
  await expect(page.getByText(`No shift matches "${code}"`)).toBeVisible()
})

test('the tabs change panels and Queues shows the save footer', async ({ page }) => {
  await signIn(page, 'admin')
  await page.goto('/configure')
  for (const name of ['Queues', 'Workforce', 'Rules']) {
    await page.getByRole('tab', { name }).click()
    await expect(page.getByRole('tab', { name })).toHaveAttribute('aria-selected', 'true')
  }
  await page.getByRole('tab', { name: 'Workforce' }).click()
  await expect(page.getByRole('button', { name: 'Discard' })).toBeDisabled()
})
