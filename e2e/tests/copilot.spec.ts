import { expect, test, type Page } from '@playwright/test'

import { PASSWORD, signIn } from './helpers'

/**
 * The Copilot (requirements 3.12), against the real stack. It answers from what the asking role
 * can already see, refuses everything else in one fixed sentence, and changes nothing. These
 * checks do not depend on which demo data exists: they look at the shape of the answer.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

const REFUSAL = "I can't share that for your role."

async function ask(page: Page, question: string): Promise<void> {
  await page.getByLabel('Your question').fill(question)
  await page.getByRole('button', { name: 'Ask' }).click()
}

test('a planner asks a coverage question and gets an answer with an Open link', async ({
  page,
}) => {
  await signIn(page, 'planner')
  await page.goto('/copilot')
  await expect(page.getByRole('heading', { name: 'Copilot', level: 1 })).toBeVisible()
  await expect(page.getByTestId('copilot-banner')).toContainText(
    'Copilot only answers from what your role can already see. It cannot change anything.',
  )

  await ask(page, 'Which queue has the biggest gap on Tuesday?')

  const answer = page.getByTestId('answer')
  await expect(answer).toBeVisible()
  await expect(answer.getByTestId('based-on')).toContainText('Based on: coverage_gaps')
  await answer.getByRole('link', { name: 'Open Planner' }).click()
  await expect(page).toHaveURL(/\/planner/)
})

test('an agent asking about a colleague gets the one refusal and no name echoed', async ({
  page,
}) => {
  await signIn(page, 'agent')
  await page.goto('/copilot')

  await ask(page, "When is Blake Agent's next leave?")

  const refusal = page.getByTestId('refusal')
  await expect(refusal).toHaveText(REFUSAL)
  // Not the name, not a source line, not a button: nothing that says whether the data exists.
  await expect(refusal).not.toContainText('Blake')
  await expect(refusal.getByTestId('based-on')).toHaveCount(0)
  await expect(refusal.getByTestId('open-action')).toHaveCount(0)
  await expect(page.getByTestId('my-message')).toContainText("Blake Agent's")

  // A person who does not exist is refused in exactly the same words.
  await page.getByLabel('Your question').fill("When is Nobody Atall's next leave?")
  await page.getByRole('button', { name: 'Ask' }).click()
  await expect(page.getByTestId('refusal')).toHaveCount(2)
  await expect(page.getByTestId('refusal').nth(1)).toHaveText(REFUSAL)
})

test('an agent can still ask about their own leave', async ({ page }) => {
  await signIn(page, 'agent')
  await page.goto('/copilot')
  await ask(page, 'What is my leave balance?')
  await expect(page.getByTestId('answer')).toBeVisible()
  await expect(page.getByTestId('answer')).toContainText('leave')
})

test('an executive is refused who was absent, and offered the rate instead', async ({ page }) => {
  await signIn(page, 'executive')
  await page.goto('/copilot')

  await ask(page, 'Who was absent yesterday?')
  await expect(page.getByTestId('refusal')).toHaveText(REFUSAL)
  await expect(page.getByRole('button', { name: 'What is the absence rate?' })).toBeVisible()

  await page.getByRole('button', { name: 'What is the absence rate?' }).click()
  const answer = page.getByTestId('answer')
  await expect(answer).toContainText('% of staff time')
  await expect(answer.getByTestId('based-on')).toContainText('absence_rate')
})

test('asking for a change only points at the screen that does it', async ({ page }) => {
  await signIn(page, 'planner')
  await page.goto('/copilot')
  await ask(page, 'Move Alex Agent to an early shift')
  const answer = page.getByTestId('answer')
  await expect(answer).toContainText("can't make that change")
  await expect(answer.getByRole('link', { name: 'Open Roster' })).toBeVisible()
})

test('the API holds the line too: an agent gets the same refusal without the screen', async ({
  page,
}) => {
  await signIn(page, 'agent')
  const token = (await page.context().cookies()).find((c) => c.name === 'csrftoken')?.value ?? ''
  const response = await page.request.post('/api/v1/copilot/ask', {
    data: { question: 'How much overtime does the team earn?' },
    headers: { 'X-CSRFToken': token },
  })
  expect(response.status()).toBe(200)
  const body = await response.json()
  expect(body.refused).toBe(true)
  expect(body.answer).toBe(REFUSAL)
  expect(body.sources).toEqual([])
})
