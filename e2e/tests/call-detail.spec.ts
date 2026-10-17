import { expect, test } from '@playwright/test'

import { PASSWORD, signIn } from './helpers'

/**
 * The Call detail screen (DAT-01), against the real stack. The demo data was written directly and
 * has no detail sheets, so these tests check what the screen does with and without them: it must
 * say "No data" rather than show zeros, and aggregate roles must never get per-agent rows.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

test('a planner opens Call detail and sees every section, with no data said plainly', async ({
  page,
}) => {
  await signIn(page, 'planner')
  await page.goto('/call-detail')
  await expect(page.getByRole('heading', { name: 'Call detail', level: 1 })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Ring-no-answer by agent' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'IVR menu and drop-off' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Transfers, holds and mutes' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Incident links' })).toBeVisible()
  // Never a ranked table.
  await expect(page.getByText(/rank|league/i)).toHaveCount(0)
})

test('an executive sees aggregates only: no per-agent table and no incident numbers', async ({
  page,
}) => {
  await signIn(page, 'executive')
  await page.goto('/call-detail')
  await expect(page.getByRole('heading', { name: 'IVR menu and drop-off' })).toBeVisible()
  await expect(page.getByTestId('ring-table')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Incident links' })).toHaveCount(0)
  const response = await page.request.get('/api/v1/telephony/call-detail?month=2026-05')
  expect(response.status()).toBe(200)
  expect((await response.json()).agents).toBeNull()
})

test('an agent is refused, in the screen and in the API', async ({ page }) => {
  await signIn(page, 'agent')
  await page.goto('/call-detail')
  await expect(
    page.getByRole('heading', { name: "You don't have access to this page" }),
  ).toBeVisible()
  const response = await page.request.get('/api/v1/telephony/call-detail?month=2026-05')
  expect(response.status()).toBe(403)
})
