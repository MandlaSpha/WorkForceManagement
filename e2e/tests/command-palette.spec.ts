import { expect, test } from '@playwright/test'

import { expectNoAccessibilityViolations, PASSWORD, signIn, signOut } from './helpers'

test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

test('the search palette opens with Ctrl+K, filters pages and goes there on Enter', async ({
  page,
}) => {
  await signIn(page, 'planner')
  await page.keyboard.press('Control+k')
  const palette = page.getByRole('dialog', { name: 'Search' })
  await expect(palette).toBeVisible()
  await expectNoAccessibilityViolations(page)
  await palette.getByRole('combobox').fill('leave')
  await expect(palette.getByRole('option', { name: /^Leave/ })).toBeVisible()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/leave$/)
  await expect(palette).toBeHidden()
  await expect(page.getByRole('navigation', { name: 'Breadcrumb' })).toContainText('Leave')
  await signOut(page)
})

test('an agent is never offered admin screens, queues or planner actions', async ({ page }) => {
  await signIn(page, 'agent')
  await page.keyboard.press('/')
  const palette = page.getByRole('dialog', { name: 'Search' })
  await palette.getByRole('combobox').fill('audit')
  await expect(palette.getByRole('option', { name: /Audit/ })).toHaveCount(0)
  await palette.getByRole('combobox').fill('')
  await expect(palette.getByRole('group', { name: 'Queues' })).toHaveCount(0)
  await palette.getByRole('option', { name: /Request leave/ }).click()
  await expect(page.getByRole('dialog', { name: 'Request leave' })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await signOut(page)
})
