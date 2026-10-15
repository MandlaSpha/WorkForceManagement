import { expect, test } from '@playwright/test'

import { expectNoAccessibilityViolations, PASSWORD, signIn, signOut } from './helpers'
import { rand } from './report'

/**
 * Importing the employee master against the real stack (DAT-06).
 *
 * A planner checks a small made-up file (nothing changes), imports it, and sees the people in the
 * list; checking the same file again says everyone is already up to date. A bad row is named by
 * reason and skipped. The employee numbers are made up for this run, so repeated runs do not meet
 * each other's people.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

test('a planner checks an employee file, imports it, and importing it again changes nothing', async ({
  page,
}) => {
  test.setTimeout(120_000)
  const id = rand(1_000_000)
  const csv = [
    'Employee No,Name,Contract,Weekly Hours,Work Mode,Favourite colour',
    `I${id}A,Import Alpha ${id},permanent,40,office,blue`,
    `I${id}B,Import Beta ${id},seasonal,,remote,red`,
    `I${id}C,Import Gamma ${id},temp,,,green`,
  ].join('\n')
  const file = { name: 'people.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) }

  await signIn(page, 'planner')
  await page.goto('/employees')
  await page.getByRole('button', { name: 'Import employees' }).click()
  await expectNoAccessibilityViolations(page)
  await page.getByLabel('Employees (.csv or .xlsx)').setInputFiles(file)
  await page.getByRole('button', { name: 'Check the file' }).click()

  // The check says what would happen and changes nothing.
  const report = page.getByTestId('emp-import-report')
  await expect(report).toContainText('If you import this file:')
  await expect(report).toContainText('2 added')
  await expect(page.getByTestId('emp-import-rejected')).toContainText(
    '1 with a contract that is not permanent or seasonal',
  )
  await expect(page.getByTestId('emp-import-ignored')).toContainText('Favourite colour')
  await expect(page.getByRole('table', { name: 'Employees' })).not.toContainText(`Import Alpha ${id}`)

  await page.getByRole('button', { name: 'Import these' }).click()
  await expect(report).toContainText('Imported:')
  const table = page.getByRole('table', { name: 'Employees' })
  await expect(table).toContainText(`Import Alpha ${id}`)
  await expect(table).toContainText(`Import Beta ${id}`)
  await expect(table).not.toContainText(`Import Gamma ${id}`) // the bad row was skipped
  // Beta had no hours: the default is shown as a default, not as a contract fact.
  const beta = table.getByRole('row').filter({ hasText: `Import Beta ${id}` })
  await expect(beta).toContainText('Default')

  // Checking the same file again: everyone is already up to date.
  await page.getByLabel('Employees (.csv or .xlsx)').setInputFiles(file)
  await page.getByRole('button', { name: 'Check the file' }).click()
  await expect(page.getByTestId('emp-import-report')).toContainText('0 added')
  await expect(page.getByTestId('emp-import-report')).toContainText('2 already up to date')
  await signOut(page)
})

test('only a planner or admin can import employees, in the screen or in the API', async ({
  page,
}) => {
  await signIn(page, 'lead')
  await page.goto('/employees')
  await expect(page.getByRole('button', { name: 'Import employees' })).toHaveCount(0)
  const csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
  const response = await page.request.post('/api/v1/scheduling/employees/import?dry_run=true', {
    headers: { 'X-CSRFToken': csrf },
    multipart: { file: { name: 'x.csv', mimeType: 'text/csv', buffer: Buffer.from('a') } },
  })
  expect(response.status()).toBe(403)
})
