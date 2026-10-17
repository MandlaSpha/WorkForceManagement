import { expect, test } from '@playwright/test'

import { expectNoAccessibilityViolations, PASSWORD, signIn, signOut } from './helpers'

/**
 * The audit log viewer against the real stack (AUD-11, AUD-12).
 *
 * The admin reads the log, sees the hash chain verdict, filters it, and downloads it. Looking at
 * the log is itself an event, so a search shows up in the next search. A planner is kept out.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

test('an admin reads, filters and downloads the audit log, and a planner cannot open it', async ({
  page,
}) => {
  await signIn(page, 'admin')
  await expect(page.getByRole('link', { name: 'Audit log' })).toBeVisible()
  await page.goto('/audit')
  await expect(page.getByTestId('chain-status')).toContainText('Hash chain intact')
  await expect(page.getByTestId('audit-table')).toBeVisible()
  await expectNoAccessibilityViolations(page)

  // Filter by what: the sign-in the test itself just made.
  await page.getByLabel('What (action)').selectOption({ label: 'Login' })
  await page.getByRole('button', { name: 'Search' }).click()
  await expect(page.getByTestId('audit-table')).toContainText('Login')

  // The CSV download is a file, and is itself recorded.
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByTestId('audit-csv').click(),
  ])
  expect(download.suggestedFilename()).toBe('audit-log.csv')

  // Searching and downloading show up as events of their own.
  await page.getByLabel('What (action)').selectOption({ label: 'Audit log exported' })
  await page.getByRole('button', { name: 'Search' }).click()
  await expect(page.getByTestId('audit-table')).toContainText('Audit log exported')
  await signOut(page)

  await signIn(page, 'planner')
  await expect(page.getByRole('link', { name: 'Audit log' })).toHaveCount(0)
  await page.goto('/audit')
  await expect(page).toHaveURL(/\/forbidden/)
})
