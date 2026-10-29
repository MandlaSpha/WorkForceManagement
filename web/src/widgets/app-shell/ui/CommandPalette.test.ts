import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { backend } from '@/test/fake-backend'
import { balancesOf, LEAVE_TYPES, requestOf } from '@/test/leave-fixtures'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'
import { swapOf } from '@/test/swap-fixtures'

async function open(role = 'planner', path = '/roster') {
  seedScheduling()
  backend.leaveTypes = LEAVE_TYPES
  backend.balances = balancesOf()
  localStorage.removeItem('wfm.nav.open')
  const view = await openScheduling(path, role)
  await screen.findByRole('navigation', { name: 'Main navigation' })
  return view
}

const palette = () => screen.findByRole('dialog', { name: 'Search' })

describe('the command palette', () => {
  it('opens from the sidebar button, with Ctrl+K, and with / outside a field', async () => {
    // Failure caught: a shortcut that only works while the sidebar has focus.
    const user = userEvent.setup()
    await open()
    await user.click(screen.getByRole('button', { name: /^Search/ }))
    await palette()
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await user.keyboard('{Control>}k{/Control}')
    await palette()
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await user.keyboard('/')
    await palette()
  })

  it('lists matching pages from closed groups and goes there on Enter', async () => {
    const user = userEvent.setup()
    const view = await open()
    await user.keyboard('/')
    const dialog = await palette()
    await user.type(within(dialog).getByRole('combobox'), 'leave')
    expect(within(dialog).getByRole('option', { name: /^Leave/ })).toBeVisible()
    await user.keyboard('{Enter}')
    await waitFor(() => expect(view.router.currentRoute.value.path).toBe('/leave'))
    expect(screen.queryByRole('dialog', { name: 'Search' })).toBeNull()
  })

  it('moves with the arrow keys and opens with the mouse too', async () => {
    const user = userEvent.setup()
    const view = await open()
    await user.keyboard('/')
    const dialog = await palette()
    const box = within(dialog).getByRole('combobox')
    expect(within(dialog).getAllByRole('option')[0]).toHaveAttribute('aria-selected', 'true')
    await user.keyboard('{ArrowDown}')
    expect(within(dialog).getAllByRole('option')[1]).toHaveAttribute('aria-selected', 'true')
    expect(box).toHaveAttribute('aria-activedescendant', expect.stringContaining('palette-opt-'))
    await user.click(within(dialog).getByRole('option', { name: /^Roster/ }))
    await waitFor(() => expect(view.router.currentRoute.value.path).toBe('/roster'))
  })

  it('says so when nothing matches', async () => {
    const user = userEvent.setup()
    await open()
    await user.keyboard('/')
    const dialog = await palette()
    await user.type(within(dialog).getByRole('combobox'), 'zzzz')
    expect(within(dialog).getByText(/Nothing matches "zzzz"/)).toBeVisible()
  })

  it('never offers a screen, queue or action the role may not use', async () => {
    // Failure caught: the palette leaking admin screens, queues or planner actions to an agent.
    const user = userEvent.setup()
    await open('agent', '/my-schedule')
    await user.keyboard('/')
    const dialog = await palette()
    await user.type(within(dialog).getByRole('combobox'), 'audit')
    expect(within(dialog).queryByRole('option', { name: /Audit/ })).toBeNull()
    await user.clear(within(dialog).getByRole('combobox'))
    expect(within(dialog).queryByRole('group', { name: 'Queues' })).toBeNull()
    expect(within(dialog).queryByRole('option', { name: /Open planner/ })).toBeNull()
    expect(within(dialog).getByRole('option', { name: /Request leave/ })).toBeVisible()
  })

  it('lists the queues the role can read and selects one in the top bar', async () => {
    const user = userEvent.setup()
    const view = await open('planner', '/roster')
    await user.keyboard('/')
    const dialog = await palette()
    const queues = await within(dialog).findByRole('group', { name: 'Queues' })
    await user.click(within(queues).getAllByRole('option')[0] as HTMLElement)
    await waitFor(() => expect(view.router.currentRoute.value.path).toBe('/planner'))
  })

  it('opens the leave form from the Request leave action', async () => {
    const user = userEvent.setup()
    await open('agent', '/my-schedule')
    await user.keyboard('/')
    const dialog = await palette()
    await user.click(within(dialog).getByRole('option', { name: /Request leave/ }))
    expect(await screen.findByRole('dialog', { name: 'Request leave' })).toBeVisible()
  })

  it('filters on this device only: typing makes no request', async () => {
    // Failure caught: a search-as-you-type call that would carry what the person typed.
    const user = userEvent.setup()
    await open()
    await user.keyboard('/')
    const dialog = await palette()
    await screen.findAllByRole('option')
    await new Promise((r) => setTimeout(r, 50))
    const before = backend.requests.length
    await user.type(within(dialog).getByRole('combobox'), 'roster')
    expect(backend.requests.length).toBe(before)
  })
})

describe('the sidebar badges', () => {
  it('shows what waits for a lead, and not their own request', async () => {
    // Failure caught: counting your own leave request as something for you to decide.
    seedScheduling()
    backend.leaveRequests = [
      requestOf({ id: 1, mine: false }),
      requestOf({ id: 2, mine: false }),
      requestOf({ id: 3, mine: true }),
    ]
    backend.swaps = [swapOf({ id: 9, status: 'awaiting_approval' })]
    localStorage.removeItem('wfm.nav.open')
    await openScheduling('/roster', 'lead')
    const nav = within(await screen.findByRole('navigation', { name: 'Main navigation' }))
    // The People group is closed, so its pill carries the sum (2 leave + 1 swap).
    const people = nav.getByRole('button', { name: /^People/ })
    await waitFor(() => expect(within(people).getByLabelText('3 waiting')).toBeVisible())
  })

  it('shows a pill on the item once its group is open, and none for an agent', async () => {
    seedScheduling()
    backend.leaveRequests = [requestOf({ id: 1, mine: false })]
    const lead = await openScheduling('/leave', 'lead')
    const nav = within(await screen.findByRole('navigation', { name: 'Main navigation' }))
    await waitFor(() => expect(nav.getByTestId('nav-badge')).toHaveTextContent('1'))
    lead.unmount()

    backend.leaveRequests = [requestOf({ id: 1, mine: false })]
    await openScheduling('/my-schedule', 'agent')
    await screen.findByRole('navigation', { name: 'Main navigation' })
    expect(screen.queryByTestId('nav-badge')).toBeNull()
  })
})
