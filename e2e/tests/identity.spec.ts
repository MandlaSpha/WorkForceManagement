import { expect, test, type Page } from '@playwright/test'

import { expectNoAccessibilityViolations, PASSWORD, signOut } from './helpers'

/**
 * Directory sign-in through a REAL OpenLDAP server (requirements AUTH-01 to AUTH-11). `just dev`
 * starts the directory, fills it with synthetic people (seed_demo_directory) and tells the API
 * about it; the people and their groups are:
 *
 *   pat  WFM Planners      lee  WFM Leads      alex  WFM Agents
 *   ash  WFM Admins        nina (no group)
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

async function directorySignIn(page: Page, username: string, password = PASSWORD): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('Sign in with').selectOption({ label: 'Company directory' })
  await page.getByLabel('Username').fill(username)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
}

const nav = (page: Page) => page.getByRole('navigation', { name: 'Main navigation' })

test('the login page offers the directory next to local accounts and is accessible', async ({
  page,
}) => {
  await page.goto('/login')

  const choice = page.getByLabel('Sign in with')
  await expect(choice).toBeVisible()
  await expect(choice.locator('option')).toHaveText(['Username and password', 'Company directory'])
  // something is actually selected, not an empty box
  await expect(choice).toHaveValue('local')
  await page.screenshot({
    path: 'screenshots/login-providers.png',
    fullPage: true,
  })
  await expectNoAccessibilityViolations(page)
})

test('a directory planner signs in and gets the planner role from their group', async ({
  page,
}) => {
  await directorySignIn(page, 'pat')

  await expect(
    page.getByRole('heading', { name: /^Good (morning|afternoon|evening)/ }),
  ).toBeVisible()
  // The signed-in name and role sit on the account card at the foot of the sidebar.
  const card = page.getByRole('button', { name: 'Account menu for Pat Planner' })
  await expect(card).toBeVisible()
  await expect(card.getByText('Pat Planner', { exact: true })).toBeVisible()
  await expect(card.getByText('Planner', { exact: true })).toBeVisible()
  await expect(nav(page).getByRole('link', { name: 'Planner' })).toBeVisible()
  await expect(nav(page).getByRole('link', { name: 'Configure' })).toHaveCount(0)
  await signOut(page)
})

test('a directory admin gets the admin screens', async ({ page }) => {
  await directorySignIn(page, 'ash')
  // Admin screens sit under Settings at the foot of the sidebar.
  await nav(page)
    .getByRole('button', { name: /^Settings/ })
    .click()
  await expect(nav(page).getByRole('link', { name: 'Configure' })).toBeVisible()
  await expect(nav(page).getByRole('link', { name: 'Audit log' })).toBeVisible()
})

test('a directory agent lands on their own schedule', async ({ page }) => {
  await directorySignIn(page, 'alex')
  await expect(page).toHaveURL(/\/my-schedule$/)
  await expect(nav(page).getByRole('link', { name: 'Planner' })).toHaveCount(0)
})

test('a team lead gets the lead role', async ({ page }) => {
  await directorySignIn(page, 'lee')
  await expect(
    page.getByRole('button', { name: /^Account menu/ }).getByText('Team lead', { exact: true }),
  ).toBeVisible()
})

test('someone in the directory but in no application group is refused', async ({ page }) => {
  await directorySignIn(page, 'nina')

  await expect(page.getByRole('alert')).toHaveText('Username or password is incorrect.')
  await expect(page).toHaveURL(/\/login/)
})

test('a wrong password, an unknown person and a person without a group all look the same', async ({
  page,
}) => {
  const message = async (username: string, password = PASSWORD) => {
    await directorySignIn(page, username, password)
    return page.getByRole('alert').textContent()
  }

  const answers = [
    await message('pat', 'definitely-wrong'),
    await message('nobody-at-all'),
    await message('nina'),
    await message('*'), // an LDAP wildcard must not match anyone
  ]

  expect(new Set(answers)).toEqual(new Set(['Username or password is incorrect.']))
})

test('a directory person cannot use the same password for a local account', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Username').fill('pat') // the local provider is selected by default
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()

  // "pat" exists as a directory-provisioned user with no usable local password (or not at all)
  await expect(page.getByRole('alert')).toHaveText('Username or password is incorrect.')
})
