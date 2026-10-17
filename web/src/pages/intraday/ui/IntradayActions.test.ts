import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { Intraday, IntradaySuggestions } from '@/entities/intraday'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

const slots = Array.from({ length: 48 }, (_, slot) => ({
  slot,
  forecast: 10,
  actual: null,
  reforecast: 12,
  scheduled: 3,
  required: 3,
  expectedRequired: 4,
}))

const day: Intraday = {
  queue: 'QueueA',
  day: '2031-03-03',
  elapsed: 22,
  hasForecast: true,
  ratio: 1.2,
  dataThrough: 21,
  serviceLevelPct: 78.5,
  slots,
  alerts: [
    { slot: 23, scheduled: 3, required: 4, short: 1, severity: 'warning' },
    { slot: 24, scheduled: 1, required: 4, short: 3, severity: 'critical' },
  ],
}

const suggestions = (over: Partial<IntradaySuggestions> = {}): IntradaySuggestions => ({
  overtimeStart: '11:30',
  overtimeEnd: '12:00',
  people: [
    { employeeId: 11, name: 'Sam Planner', weekMinutes: 480 },
    { employeeId: 10, name: 'Alex Agent', weekMinutes: 960 },
  ],
  breaks: [
    {
      activityId: 801,
      employee: 'Alex Agent',
      kind: 'lunch',
      start: '11:30',
      end: '12:30',
      moveTo: '13:00',
      slots: 2,
    },
  ],
  ...over,
})

async function open(role = 'planner', found: IntradaySuggestions | null = suggestions()) {
  seedScheduling()
  backend.intraday = day
  backend.suggestions = found
  backend.activities = [
    {
      id: 801,
      assignmentId: 1,
      employeeId: 10,
      employee: 'Alex Agent',
      day: '2031-03-03',
      shift: 'D1',
      kind: 'lunch',
      startTime: '11:30',
      endTime: '12:30',
      slots: 2,
      offsetSlots: 5,
    },
  ]
  return openScheduling('/intraday', role)
}

const whatCanIDo = () => screen.findByRole('button', { name: 'What can be done about 11:30' })

describe('acting on a short half-hour', () => {
  it('offers people for overtime, lightest week first, linking to the pre-filled request', async () => {
    // Failure caught: an alert with no way to act, or a link that does not carry the person, the
    // day and the whole short stretch (half-hours 23 and 24 are both short: one 11:30-12:30 ask).
    const user = userEvent.setup()
    await open()
    await user.click(await whatCanIDo())
    const panel = await screen.findByTestId('actions-23')
    const list = await within(panel).findByRole('list', { name: 'People who could cover' })
    const names = within(list)
      .getAllByRole('listitem')
      .map((li) => li.textContent)
    expect(names[0]).toContain('Sam Planner')
    expect(names[1]).toContain('Alex Agent')
    const link = within(list).getByRole('link', { name: 'Ask Sam Planner for overtime' })
    const href = new URL(link.getAttribute('href') as string, 'http://x')
    expect(href.pathname).toBe('/overtime')
    expect(Object.fromEntries(href.searchParams)).toEqual({
      day: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      from: '11:30',
      to: '12:30',
      employeeId: '11',
    })
    expect(backend.suggestionQueries.at(-1)).toMatchObject({ slot: '23' })
  })

  it('moves a break in one click and sends the new time with the CSRF token', async () => {
    // Failure caught: a move that sends the wrong time, drops the CSRF token, or leaves the
    // break offered after it has moved.
    const user = userEvent.setup()
    await open()
    await user.click(await whatCanIDo())
    await user.click(await screen.findByRole('button', { name: 'Move to 13:00' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toEqual({
      method: 'POST',
      path: '/api/v1/scheduling/roster/activities/801/move',
      body: { startTime: '13:00' },
      csrf: 'test-csrf-token',
    })
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Move to 13:00' })).toBeNull())
  })

  it('says so when nobody can be asked and no break can move', async () => {
    const user = userEvent.setup()
    await open('planner', suggestions({ people: [], breaks: [] }))
    await user.click(await whatCanIDo())
    expect(await screen.findByText(/Nobody skilled on this queue is free/)).toBeVisible()
    expect(screen.queryByText('Move a break')).toBeNull()
  })

  it('shows why a move was refused', async () => {
    const user = userEvent.setup()
    await open()
    backend.nextProblem = {
      status: 422,
      code: 'activity.overlap',
      title: 'Activity refused',
      detail: 'That overlaps another break or activity in the shift.',
    }
    await user.click(await whatCanIDo())
    await user.click(await screen.findByRole('button', { name: 'Move to 13:00' }))
    expect(await screen.findByTestId('move-error')).toHaveTextContent('overlaps another break')
  })

  it('shows a lead the alerts but no way to act', async () => {
    // Failure caught: a lead being offered staff names and the move they may not make.
    await open('lead', null)
    expect(await screen.findByTestId('alert-24')).toBeVisible()
    expect(screen.queryByRole('button', { name: /What can be done/ })).toBeNull()
    expect(backend.suggestionQueries).toEqual([])
  })
})
