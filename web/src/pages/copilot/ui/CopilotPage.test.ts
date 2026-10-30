import { fireEvent, screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { backend } from '@/test/fake-backend'
import { renderApp } from '@/test/render-app'

async function open(role = 'planner') {
  backend.signedIn = { username: role, displayName: `Test ${role}`, role }
  document.cookie = 'csrftoken=test-csrf-token'
  return renderApp('/copilot')
}

async function ask(text: string) {
  const box = await screen.findByLabelText('Your question')
  await fireEvent.update(box, text)
  await fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
}

const REFUSAL = "I can't share that for your role."

describe('copilot', () => {
  it.each(['agent', 'lead', 'planner', 'admin', 'executive', 'customer_ops'])(
    'is in the menu for %s, under Insight',
    async (role) => {
      await open(role)
      const nav = within(await screen.findByRole('navigation', { name: 'Main navigation' }))
      expect(nav.getByRole('link', { name: 'Copilot' })).toHaveAttribute('href', '/copilot')
    },
  )

  it('is hidden from the menu when the feature is switched off', async () => {
    backend.features = backend.features.filter((f) => f !== 'copilot')
    await open()
    const nav = within(await screen.findByRole('navigation', { name: 'Main navigation' }))
    expect(nav.queryByRole('link', { name: 'Copilot' })).toBeNull()
  })

  it('shows an answer with its source line and an Open button that links to the screen', async () => {
    backend.copilotReply = {
      answer: 'On Tuesday 2026-05-26, QueueAlpha has the biggest gap: 20 people-half-hours short.',
      refused: false,
      sources: [{ tool: 'coverage_gaps', rows: 1 }],
      actions: [{ label: 'Open Planner', path: '/planner' }],
      suggestions: ['Why is Tuesday short?'],
    }
    await open()
    await ask('Which queue has the biggest gap on Tuesday?')

    const card = await screen.findByTestId('answer')
    expect(card).toHaveTextContent('QueueAlpha has the biggest gap')
    expect(within(card).getByTestId('based-on')).toHaveTextContent(
      'Based on: coverage_gaps (1 row)',
    )
    expect(within(card).getByRole('link', { name: 'Open Planner' })).toHaveAttribute(
      'href',
      '/planner',
    )
    expect(backend.copilotQuestions).toEqual(['Which queue has the biggest gap on Tuesday?'])
    // The chips are now what the API says this role can ask.
    expect((await screen.findAllByTestId('suggestion')).map((b) => b.textContent?.trim())).toEqual([
      'Why is Tuesday short?',
    ])
  })

  it('asks a suggested question when its chip is pressed', async () => {
    await open('agent')
    await fireEvent.click(await screen.findByRole('button', { name: /What is my leave balance/ }))
    await screen.findByTestId('answer')
    expect(backend.copilotQuestions).toEqual(['What is my leave balance?'])
  })

  it('draws the answer as text, never as markup', async () => {
    // Failure caught: v-html (or any HTML rendering) of text that came from data: a name or a
    // remark containing markup would run in the person's browser.
    backend.copilotReply = {
      answer: '<img src=x onerror=alert(1)> <b>bold</b> <script>window.hacked=1</script>',
      refused: false,
      sources: [],
      actions: [],
      suggestions: [],
    }
    await open()
    await ask('anything')

    const card = await screen.findByTestId('answer')
    expect(card.querySelector('img, b, script')).toBeNull()
    expect(card).toHaveTextContent('<img src=x onerror=alert(1)> <b>bold</b>')
    expect((window as unknown as { hacked?: number }).hacked).toBeUndefined()
  })

  it('draws two different refusals the same way, with nothing that hints at why', async () => {
    // Failure caught: a refusal that looks different (colour, extra line, source, button) when
    // the data exists, which would confirm that it does.
    backend.copilotReply = {
      answer: REFUSAL,
      refused: true,
      sources: [],
      actions: [],
      suggestions: ['What is my leave balance?'],
    }
    await open('agent')
    await ask("When is Zandile's next leave?")
    await screen.findByTestId('refusal')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled())
    await ask('When is Nobody Real next leave?')

    await waitFor(() => expect(screen.getAllByTestId('refusal')).toHaveLength(2))
    const cards = screen.getAllByTestId('refusal')
    expect(cards[0]!.outerHTML.replace(/data-v-\w+=""/g, '')).toBe(
      cards[1]!.outerHTML.replace(/data-v-\w+=""/g, ''),
    )
    expect(cards[0]).toHaveTextContent(REFUSAL)
    expect(within(cards[0]!).queryByTestId('based-on')).toBeNull()
    expect(within(cards[0]!).queryByTestId('open-action')).toBeNull()
    expect(screen.queryByTestId('copilot-error')).toBeNull()
  })

  it('remembers nothing outside the page: no local or session storage is written', async () => {
    // Failure caught: the conversation saved in the browser (where the next person on a shared
    // computer could read it).
    await open()
    const before = JSON.stringify([{ ...localStorage }, { ...sessionStorage }])
    await ask('Which queue has the biggest gap on Tuesday?')
    await screen.findByTestId('answer')
    expect(JSON.stringify([{ ...localStorage }, { ...sessionStorage }])).toBe(before)
    expect(JSON.stringify({ ...localStorage })).not.toContain('biggest gap')
  })

  it('shows the rate limit as a plain message and keeps the page usable', async () => {
    backend.copilotProblem = {
      status: 429,
      code: 'copilot.rate_limited',
      detail:
        'You have asked a lot of questions in a short time. Please wait a minute and try again.',
    }
    await open()
    await ask('Why is Tuesday short?')

    const error = await screen.findByTestId('copilot-error')
    expect(error).toHaveTextContent('Please wait a minute and try again.')
    expect(screen.getByLabelText('Your question')).toBeEnabled()
  })

  it.each([
    [403, 'auth.forbidden', 'Your role may not use the Copilot.'],
    [403, 'feature.disabled', 'The Copilot is not part of your plan.'],
    [404, 'resource.not_found', 'The Copilot is not available here.'],
  ])('explains a %i (%s) in plain words', async (status, code, words) => {
    backend.copilotProblem = { status, code, detail: 'internal detail that must not show' }
    await open()
    await ask('Why is Tuesday short?')

    const error = await screen.findByTestId('copilot-error')
    expect(error).toHaveTextContent(words)
    expect(error).not.toHaveTextContent('internal detail')
  })

  it('counts the characters and refuses a question over 300', async () => {
    await open()
    const box = await screen.findByLabelText('Your question')

    await fireEvent.update(box, 'x'.repeat(300))
    expect(screen.getByTestId('char-count')).toHaveTextContent('300 of 300 characters')
    expect(screen.getByRole('button', { name: 'Ask' })).toBeEnabled()

    await fireEvent.update(box, 'x'.repeat(301))
    expect(screen.getByTestId('char-count')).toHaveTextContent('too long')
    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled()
    expect(backend.copilotQuestions).toEqual([])
  })

  it('does not ask an empty question', async () => {
    await open()
    await screen.findByLabelText('Your question')
    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled()
  })

  it('announces new answers politely and puts focus back in the composer', async () => {
    // Failure caught: a screen-reader user never hearing the answer, or losing their place.
    await open()
    const log = await screen.findByRole('log')
    expect(log).toHaveAttribute('aria-live', 'polite')

    await ask('Why is Tuesday short?')
    await within(log).findByTestId('answer')

    await waitFor(() => expect(screen.getByLabelText('Your question')).toHaveFocus())
  })

  it('keeps the conversation in the page only: leaving and coming back starts empty', async () => {
    const view = await open()
    await ask('Why is Tuesday short?')
    await screen.findByTestId('answer')

    await view.router.push('/leave')
    await view.router.push('/copilot')

    await screen.findByLabelText('Your question')
    expect(screen.queryByTestId('answer')).toBeNull()
    expect(screen.queryByTestId('my-message')).toBeNull()
  })
})
