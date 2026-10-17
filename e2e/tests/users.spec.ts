import { expect, test } from '@playwright/test'

import { expectNoAccessibilityViolations, PASSWORD, signIn, signOut } from './helpers'
import { rand } from './report'

/**
 * User administration against the real stack (CFG-04).
 *
 * An admin adds a local account with a temporary password; the person is made to choose their own
 * before anything else opens; the admin then switches the account off and it can no longer sign
 * in. The username is made up for this run, so repeated runs do not meet each other's accounts.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

const TEMPORARY = 'Temporary-Passphrase-1'
const OWN = 'My-Own-Passphrase-2'

test('an admin adds a user, who must choose their own password, and can then switch them off', async ({
  page,
}) => {
  test.setTimeout(120_000)
  const username = `e2e-user-${rand(1_000_000)}`

  await signIn(page, 'admin')
  await page.goto('/users')
  await expectNoAccessibilityViolations(page)
  const form = page.getByRole('form', { name: 'Add a user' })
  await form.getByLabel('Username').fill(username)
  await form.getByLabel('First name').fill('Test')
  await form.getByLabel('Last name').fill('Person')
  await form.getByLabel('Role').selectOption({ label: 'Agent' })
  await form.getByLabel('Temporary password').fill(TEMPORARY)
  await form.getByRole('button', { name: 'Add user' }).click()
  await expect(page.getByTestId('create-result')).toContainText('will be asked to change it')
  const row = page.getByTestId(`user-${username}`)
  await expect(row).toContainText('must choose a password')
  await signOut(page)

  // The new person signs in and is sent to choose their own password first.
  await signIn(page, username, TEMPORARY, { expectSuccess: false })
  await expect(page.getByTestId('forced-notice')).toBeVisible()
  await page.goto('/leave') // trying to go elsewhere does not work
  await expect(page.getByRole('form', { name: 'Change your password' })).toBeVisible()
  await expectNoAccessibilityViolations(page)
  const change = page.getByRole('form', { name: 'Change your password' })
  await change.getByLabel('Your current password').fill(TEMPORARY)
  await change.getByLabel('New password', { exact: true }).fill(OWN)
  await change.getByLabel('New password again').fill(OWN)
  await change.getByRole('button', { name: 'Change password' }).click()
  await expect(page.getByRole('button', { name: /^Account menu/ })).toBeVisible()
  await signOut(page)

  // Their old temporary password no longer works; their own does.
  await signIn(page, username, TEMPORARY, { expectSuccess: false })
  await expect(page.getByRole('alert')).toBeVisible()
  await signIn(page, username, OWN)
  await signOut(page)

  // The admin switches them off; they can no longer sign in.
  await signIn(page, 'admin')
  await page.goto('/users')
  await page.getByRole('button', { name: `Switch off ${username}` }).click()
  await expect(page.getByTestId(`user-${username}`)).toContainText('Switched off')
  await signOut(page)
  await signIn(page, username, OWN, { expectSuccess: false })
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByRole('button', { name: /^Account menu/ })).toHaveCount(0)
})

test('only an admin may use user administration, in the screen or in the API', async ({ page }) => {
  await signIn(page, 'planner')
  await page.goto('/users')
  await expect(
    page.getByRole('heading', { name: "You don't have access to this page" }),
  ).toBeVisible()
  expect((await page.request.get('/api/v1/users')).status()).toBe(403)
  const csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
  const made = await page.request.post('/api/v1/users', {
    headers: { 'X-CSRFToken': csrf },
    data: { username: 'sneaky', firstName: 'S', lastName: 'S', role: 'admin', password: 'x' },
  })
  expect(made.status()).toBe(403)
})
