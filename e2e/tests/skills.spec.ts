import { expect, test, type Page } from '@playwright/test'

import { expectNoAccessibilityViolations, PASSWORD, signIn, signOut } from './helpers'

/**
 * Skills and wellbeing against the real stack (SKL-01, WEL-01, WEL-02). A planner records a
 * credential for someone, finds them through the filter, and removes it again; the wellbeing
 * prompts reach the lead and the planner and nobody else.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

async function csrf(page: Page): Promise<string> {
  return (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
}

test('a planner records a credential, finds who holds it, and removes it', async ({ page }) => {
  // Unique per run, so repeated runs and parallel specs never meet each other's data.
  const name = `Lang${Date.now()}`
  await signIn(page, 'planner')
  const employees = await (await page.request.get('/api/v1/scheduling/employees')).json()
  const person = employees[0]
  expect(person, 'the demo data has employees').toBeTruthy()

  await page.goto('/skills')
  await page.getByLabel('Employee').selectOption(String(person.id))
  const editor = page.getByTestId('credential-editor')
  await editor.getByRole('button', { name: 'Add credential' }).click()
  const rows = await editor.getByRole('listitem').count()
  await editor.getByLabel(`Kind of credential ${rows}`).selectOption('language')
  await editor.getByLabel(`Name of credential ${rows}`).fill(name)
  await editor.getByRole('button', { name: 'Save credentials' }).click()
  await expect(page.getByTestId('credentials-saved')).toBeVisible()
  await expect(page.getByTestId('held')).toContainText(`Language: ${name}`)
  await expectNoAccessibilityViolations(page)

  // The filter the roster can use finds exactly that person.
  await page.getByLabel('Credential name').fill(name)
  await expect(page.getByTestId('holders')).toContainText(person.empNo)

  // Remove it again so the demo data is left as found.
  await editor.getByRole('button', { name: new RegExp(`Remove credential ${rows}`) }).click()
  await editor.getByRole('button', { name: 'Save credentials' }).click()
  await expect(page.getByRole('list', { name: 'Credentials held' }).getByText(name)).toHaveCount(0)
})

test('wellbeing prompts reach the lead and the planner, never an agent or an executive', async ({
  page,
}) => {
  await signIn(page, 'lead')
  await page.goto('/wellbeing')
  await expect(page.getByTestId('how-it-works')).toContainText('not a score')
  await expectNoAccessibilityViolations(page)
  const asLead = await page.request.get('/api/v1/wellbeing/flags')
  expect(asLead.status()).toBe(200)
  // Facts only: never a score or a ranking in the answer.
  expect(Object.keys(await asLead.json()).sort()).toEqual(['asOf', 'people'])
  await signOut(page)

  await signIn(page, 'planner')
  expect((await page.request.get('/api/v1/wellbeing/flags')).status()).toBe(200)
  expect((await page.request.get('/api/v1/skills/gaps?start=2026-06-01&days=7')).status()).toBe(200)
  await signOut(page)

  for (const username of ['agent', 'executive']) {
    await signIn(page, username)
    expect((await page.request.get('/api/v1/wellbeing/flags')).status()).toBe(403)
    expect((await page.request.get('/api/v1/skills/gaps?start=2026-06-01&days=7')).status()).toBe(
      403,
    )
    const put = await page.request.put('/api/v1/skills/employees/1/credentials', {
      headers: { 'X-CSRFToken': await csrf(page) },
      data: { credentials: [] },
    })
    expect(put.status()).toBe(403)
    await signOut(page)
  }
})
