import userEvent from '@testing-library/user-event'
import { screen, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { backend } from '@/test/fake-backend'
import { renderApp } from '@/test/render-app'

async function open(role = 'planner', path = '/roster') {
  backend.signedIn = { username: role, displayName: 'Test', role } as never
  localStorage.removeItem('wfm.nav.open') // the shared setup opens every group; these test closing
  await renderApp(path)
  return within(await screen.findByRole('navigation', { name: 'Main navigation' }))
}

describe('the sidebar groups', () => {
  it('opens only the group you are in and closes the rest', async () => {
    // Failure caught: every group open at once, which is the long scrolling menu this replaces.
    const nav = await open('planner', '/roster')
    expect(nav.getByRole('button', { name: /^Operate/ })).toHaveAttribute('aria-expanded', 'true')
    expect(nav.getByRole('button', { name: /^Insight/ })).toHaveAttribute('aria-expanded', 'false')
    expect(nav.queryByRole('link', { name: 'Peaks and troughs' })).toBeNull() // closed: out of reach
  })

  it('opens a group on click, closes the one that was open, and remembers it', async () => {
    // Failure caught: groups piling up open until the menu scrolls again.
    const user = userEvent.setup()
    const nav = await open('planner', '/roster')
    await user.click(nav.getByRole('button', { name: /^Insight/ }))
    expect(nav.getByRole('button', { name: /^Insight/ })).toHaveAttribute('aria-expanded', 'true')
    expect(nav.getByRole('button', { name: /^Operate/ })).toHaveAttribute('aria-expanded', 'false')
    expect(JSON.parse(localStorage.getItem('wfm.nav.open') ?? '[]')).toEqual(['Insight'])
  })

  it('keeps the group you are in open when nothing else was chosen', async () => {
    // Failure caught: the screen you are looking at vanishing from the menu.
    const user = userEvent.setup()
    const nav = await open('planner', '/roster')
    await user.click(nav.getByRole('button', { name: /^Operate/ }))
    expect(nav.getByRole('link', { name: 'Roster' })).toBeVisible()
  })

  it('points each group button at an id with no spaces', async () => {
    // Failure caught: aria-controls="nav-My work", an invalid id the accessibility check rejects.
    const nav = await open('agent', '/my/schedule')
    const target = nav.getByRole('button', { name: /^My work/ }).getAttribute('aria-controls') ?? ''
    expect(target).not.toMatch(/\s/)
    expect(document.getElementById(target)).not.toBeNull()
  })

  it('says how many screens are in each group', async () => {
    const nav = await open('planner', '/roster')
    expect(nav.getByRole('button', { name: /^Insight/ })).toHaveTextContent(/\d+$/)
  })
})

describe('finding a screen', () => {
  it('lists matching screens from every group, including closed ones, and leaves on Enter', async () => {
    const user = userEvent.setup()
    const nav = await open('planner', '/roster')
    await user.type(screen.getByLabelText('Find a screen'), 'leave')
    expect(nav.getByRole('link', { name: /^Leave/ })).toBeVisible()
    await user.keyboard('{Enter}')
    expect(nav.queryByLabelText('Matching screens')).toBeNull() // the search clears after going
  })

  it('says so when nothing matches', async () => {
    const user = userEvent.setup()
    const nav = await open('planner', '/roster')
    await user.type(screen.getByLabelText('Find a screen'), 'zzzz')
    expect(nav.getByText(/No screen matches "zzzz"/)).toBeVisible()
  })

  it('never offers a screen the role may not open', async () => {
    // Failure caught: the finder leaking the names of admin screens to an agent.
    const user = userEvent.setup()
    const nav = await open('agent', '/my/schedule')
    await user.type(screen.getByLabelText('Find a screen'), 'audit')
    expect(nav.queryByRole('link', { name: /Audit/ })).toBeNull()
  })

  it('jumps to the finder with Ctrl+K', async () => {
    const user = userEvent.setup()
    await open('planner', '/roster')
    await user.keyboard('{Control>}k{/Control}')
    expect(screen.getByLabelText('Find a screen')).toHaveFocus()
  })
})
