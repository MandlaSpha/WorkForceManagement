import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'
import { overviewOf } from '@/test/scheduling-fixtures'

const nav = () => within(screen.getByRole('navigation', { name: 'Main navigation' }))

describe('the foot of the sidebar', () => {
  it('keeps admin screens under Settings, once, and opens them on click', async () => {
    // Failure caught: Configure and Audit log shown twice (in a group and under Settings), or
    // Settings that cannot be opened from the keyboard.
    seedScheduling()
    const user = userEvent.setup()
    await openScheduling('/roster', 'admin')
    const settings = await nav().findByRole('button', { name: /^Settings/ })
    expect(settings).toHaveAttribute('aria-expanded', 'false')
    expect(nav().queryByRole('button', { name: /^Admin/ })).toBeNull()
    await user.click(settings)
    expect(settings).toHaveAttribute('aria-expanded', 'true')
    expect(nav().getAllByRole('link', { name: 'Configure' })).toHaveLength(1)
    expect(nav().getByRole('link', { name: 'Audit log' })).toBeVisible()
  })

  it('shows no Settings or Help to a role with no admin screens', async () => {
    // Failure caught: a dead Settings button, or a Help link to a screen that does not exist.
    seedScheduling()
    await openScheduling('/roster', 'planner')
    await nav().findByRole('link', { name: 'Roster' })
    expect(nav().queryByRole('button', { name: /^Settings/ })).toBeNull()
    expect(nav().queryByRole('link', { name: 'Help' })).toBeNull()
  })

  it("shows the planner this week's coverage from the overview the API returns", async () => {
    // Failure caught: invented numbers, or a card drawn before the figures arrive.
    seedScheduling()
    backend.overview = overviewOf()
    await openScheduling('/roster', 'planner')
    const card = await screen.findByTestId('coverage-card')
    expect(card).toHaveTextContent('96%')
    expect(card).toHaveTextContent('92 of 96 half-hours covered')
    expect(within(card).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '96')
  })

  it('draws no coverage card when the overview fails', async () => {
    // Failure caught: a placeholder card on error.
    seedScheduling()
    backend.overview = null
    await openScheduling('/roster', 'planner')
    await nav().findByRole('link', { name: 'Roster' })
    await waitFor(() => expect(screen.queryByTestId('coverage-card')).toBeNull())
  })

  it('draws no coverage card for an agent', async () => {
    // Failure caught: a planner-only card shown to an agent.
    seedScheduling()
    backend.overview = overviewOf()
    await openScheduling('/my-schedule', 'agent')
    await nav().findByRole('link', { name: 'My schedule' })
    expect(screen.queryByTestId('coverage-card')).toBeNull()
  })

  it('opens the account actions upward from the user card and closes on Escape', async () => {
    // Failure caught: account actions lost with the top-bar chip, or a menu Escape cannot close.
    seedScheduling()
    const user = userEvent.setup()
    await openScheduling('/roster', 'planner')
    const card = await screen.findByRole('button', { name: /^Account menu/ })
    await user.click(card)
    expect(screen.getByRole('menuitem', { name: 'Change password' })).toBeVisible()
    expect(screen.getByRole('menuitem', { name: 'Sign out' })).toBeVisible()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('menu')).toBeNull()
    expect(card).toHaveFocus()
  })
})
