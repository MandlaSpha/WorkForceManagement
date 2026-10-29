import AxeBuilder from '@axe-core/playwright'
import { expect, type Page } from '@playwright/test'

import { addDays, buildReport, randomFirstId, tenCalls, XLSX } from './report'

export const PASSWORD = process.env.WFM_DEMO_PASSWORD ?? ''

/** Signs in and, unless told the attempt should fail, waits until the session really exists. A
 * test that navigates immediately after the click would abort the in-flight login request. */
export async function signIn(
  page: Page,
  username: string,
  password = PASSWORD,
  { expectSuccess = true }: { expectSuccess?: boolean } = {},
): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('Username').fill(username)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  // The account card lives at the foot of the sidebar, which is a closed drawer on a phone, so
  // "signed in" means the card exists, not that it is on screen.
  if (expectSuccess)
    await expect(page.getByRole('button', { name: /^Account menu/ })).toBeAttached()
}

/** Opens the account menu from the user card at the foot of the sidebar; on a phone the sidebar
 * is a drawer, so it is opened first. */
export async function openAccountMenu(page: Page): Promise<void> {
  const card = page.getByRole('button', { name: /^Account menu/ })
  if (!(await card.isVisible())) await page.getByRole('button', { name: 'Open navigation' }).click()
  await card.click()
}

export async function signOut(page: Page): Promise<void> {
  await openAccountMenu(page)
  await page.getByRole('menuitem', { name: 'Sign out' }).click()
  await expect(page).toHaveURL(/\/login/)
}

/** Fails the test on any WCAG 2.1 A/AA violation, listing each one so the cause is obvious. */
export async function expectNoAccessibilityViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()
  const summary = results.violations.map(
    (v) =>
      `${v.id} (${v.impact}): ${v.help} -> ${v.nodes
        .map((n) => `${n.target.join(' ')} ${JSON.stringify(n.any[0]?.data ?? {})}`)
        .join(' | ')}`,
  )
  expect(summary, summary.join('\n')).toEqual([])
}

/** The Monday after today's week, in the same zone the app shows. */
export function nextMonday(): string {
  const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Africa/Johannesburg' })
  const day = new Date(`${today}T00:00:00Z`)
  const toMonday = (8 - day.getUTCDay()) % 7 || 7
  return addDays(today, toMonday)
}

export async function importDay(page: Page, date: string, queue: string): Promise<void> {
  const buffer = await buildReport({ date, firstId: randomFirstId(), calls: tenCalls(), queue })
  await page.goto('/imports')
  await page
    .getByLabel('Call detail report (.xlsx)')
    .setInputFiles({ name: `${date}.xlsx`, mimeType: XLSX, buffer })
  await page.getByRole('button', { name: 'Import report' }).click()
  // Reading a workbook can take a few seconds on a busy machine.
  await expect(page.getByTestId('reconciles')).toBeVisible({ timeout: 20_000 })
}
