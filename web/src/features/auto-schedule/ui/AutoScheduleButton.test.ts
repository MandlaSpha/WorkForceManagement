import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

const PLACEMENTS = [
  { employeeId: 7, employee: 'Sam Planner', day: '2026-05-27', shift: 'D1' },
  { employeeId: 8, employee: 'Alex Agent', day: '2026-05-28', shift: 'E1' },
]

async function open(role = 'planner') {
  seedScheduling()
  backend.autoProposal = {
    status: 'optimal',
    placements: PLACEMENTS,
    shortBefore: 40,
    shortAfter: 6,
    overAfter: 2,
    kept: 3,
  }
  const user = userEvent.setup()
  await openScheduling('/roster', role)
  return user
}

describe('auto-schedule', () => {
  it('previews what it would add and the gap before and after, without applying anything', async () => {
    const user = await open()
    await user.click(await screen.findByRole('button', { name: 'Auto-schedule' }))
    const summary = await screen.findByTestId('auto-summary')
    expect(summary).toHaveTextContent('2 shifts would be added to the 3 already rostered')
    expect(summary).toHaveTextContent('40 now')
    expect(summary).toHaveTextContent('6 after')
    expect(summary).toHaveTextContent('2 would have one person too many')
    const list = screen.getByRole('list', { name: 'Shifts to be added' })
    expect(within(list).getAllByRole('listitem')).toHaveLength(2)
    // Failure caught: the preview filling the roster before the planner has seen it.
    expect(backend.writes.map((w) => w.path)).toEqual([
      '/api/v1/scheduling/roster/auto-schedule/preview',
    ])
    expect(backend.writes[0]).toMatchObject({
      body: { queueId: 1, weekStart: '2026-05-25' },
      csrf: 'test-csrf-token',
    })
  })

  it('applies only when asked, sending nothing but the queue and the week', async () => {
    // Failure caught: the apply request carrying the shifts, which the server must never trust.
    const user = await open()
    await user.click(await screen.findByRole('button', { name: 'Auto-schedule' }))
    await user.click(await screen.findByRole('button', { name: 'Apply these shifts' }))
    await waitFor(() => expect(backend.writes).toHaveLength(2))
    expect(backend.writes[1]).toMatchObject({
      method: 'POST',
      path: '/api/v1/scheduling/roster/auto-schedule',
      body: { queueId: 1, weekStart: '2026-05-25' },
      csrf: 'test-csrf-token',
    })
    expect(await screen.findByTestId('auto-result')).toHaveTextContent('Added 2 shifts')
  })

  it('says how many the roster refused instead of claiming they were all added', async () => {
    const user = await open()
    backend.autoSkipped = { 'roster.over_hours': 1 }
    await user.click(await screen.findByRole('button', { name: 'Auto-schedule' }))
    await user.click(await screen.findByRole('button', { name: 'Apply these shifts' }))
    const result = await screen.findByTestId('auto-result')
    expect(result).toHaveTextContent('Added 1 shift.')
    expect(result).toHaveTextContent('1 could not be added')
  })

  it('offers nothing to apply when no shift would help', async () => {
    const user = await open()
    backend.autoProposal = { ...backend.autoProposal, placements: [] }
    await user.click(await screen.findByRole('button', { name: 'Auto-schedule' }))
    expect(await screen.findByTestId('auto-summary')).toHaveTextContent('0 shifts would be added')
    expect(screen.queryByRole('button', { name: 'Apply these shifts' })).toBeNull()
    // Failure caught: "0 shifts" with a gap still open and no word on why.
    expect(screen.getByTestId('auto-nothing-fits')).toHaveTextContent('Add a shorter shift')
  })

  it('does not blame the rules when there is nothing left to fill', async () => {
    const user = await open()
    backend.autoProposal = {
      ...backend.autoProposal,
      placements: [],
      shortBefore: 0,
      shortAfter: 0,
    }
    await user.click(await screen.findByRole('button', { name: 'Auto-schedule' }))
    await screen.findByTestId('auto-summary')
    expect(screen.queryByTestId('auto-nothing-fits')).toBeNull()
  })

  it('says plainly when no roster keeps every rule', async () => {
    const user = await open()
    backend.autoProposal = { ...backend.autoProposal, status: 'none', placements: [] }
    await user.click(await screen.findByRole('button', { name: 'Auto-schedule' }))
    expect(await screen.findByTestId('auto-proposal')).toHaveTextContent('No roster could be found')
  })

  it('says when the search ran out of time', async () => {
    const user = await open()
    backend.autoProposal = { ...backend.autoProposal, status: 'feasible' }
    await user.click(await screen.findByRole('button', { name: 'Auto-schedule' }))
    expect(await screen.findByText(/stopped on its time limit/)).toBeVisible()
  })

  it('shows why it could not run', async () => {
    const user = await open()
    backend.nextProblem = {
      status: 409,
      code: 'autoschedule.no_forecast',
      title: 'Auto-schedule refused',
      detail: 'There is no published forecast for this week.',
    }
    await user.click(await screen.findByRole('button', { name: 'Auto-schedule' }))
    expect(await screen.findByTestId('auto-error')).toHaveTextContent('no published forecast')
  })

  it('can be dismissed without changing anything', async () => {
    const user = await open()
    await user.click(await screen.findByRole('button', { name: 'Auto-schedule' }))
    await user.click(await screen.findByRole('button', { name: 'Dismiss' }))
    expect(screen.queryByTestId('auto-proposal')).toBeNull()
    expect(backend.writes).toHaveLength(1)
  })
})

describe('who is offered it', () => {
  it('is hidden from a lead, who only reads the roster', async () => {
    await open('lead')
    await screen.findByText(/You can read the roster here/)
    expect(screen.queryByRole('button', { name: 'Auto-schedule' })).toBeNull()
  })

  it('is hidden once the week is published', async () => {
    seedScheduling()
    backend.roster = { ...backend.roster!, status: 'published' }
    await openScheduling('/roster', 'planner')
    await screen.findByText(/This week is published/)
    expect(screen.queryByRole('button', { name: 'Auto-schedule' })).toBeNull()
  })
})
