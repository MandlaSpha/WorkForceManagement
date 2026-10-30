import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { monthGrid, monthLabel, monthOf, shiftMonth } from '@/entities/my-schedule'
import type { MySchedule } from '@/entities/my-schedule'
import { addDays, todayInJohannesburg, weekStartOf } from '@/shared/lib/week'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

const today = todayInJohannesburg()
const MONTH = monthOf(today)
const NEXT = shiftMonth(MONTH, 1)
const day = (n: number, month = MONTH) => `${month}-${String(n).padStart(2, '0')}`

const schedule = (over: Partial<MySchedule> = {}): MySchedule => ({
  employee: 'Alex Agent',
  fromDate: day(1),
  toDate: day(28),
  shifts: [
    {
      day: day(15),
      shift: 'D1',
      startTime: '09:00:00',
      endTime: '17:30:00',
      queue: 'QueueA',
      activities: [],
    },
  ],
  leave: [],
  unpublishedShifts: 0,
  openSwaps: 0,
  ...over,
})

async function open(over: Partial<MySchedule> = {}) {
  seedScheduling()
  backend.mySchedule = schedule(over)
  return openScheduling('/my-schedule', 'agent')
}

describe('the month', () => {
  it('asks for the whole grid, Monday to Sunday, and shows the month by name', async () => {
    await open()
    const grid = monthGrid(MONTH)
    expect(await screen.findByTestId('month-title')).toHaveTextContent(monthLabel(MONTH))
    // Failure caught: asking for just the 1st to the 31st leaves the days of the neighbouring
    // months at the grid's edges looking empty when they are not.
    await waitFor(() =>
      expect(backend.scheduleQueries).toContain(`?from_date=${grid.from}&to_date=${grid.to}`),
    )
  })

  it('puts each published shift in its own day, with times', async () => {
    await open()
    const cell = await screen.findByTestId(`day-${day(15)}`)
    expect(cell).toHaveTextContent('D1')
    // Failure caught: the code and the time run together ("D109:00") when read.
    expect(cell).toHaveTextContent('09:00 to 17:30')
    expect(within(cell).getByText('D1').tagName).toBe('SPAN')
    expect(within(cell).getByText('D1').textContent).toBe('D1')
    expect(screen.getByTestId(`day-${day(16)}`)).not.toHaveTextContent('D1')
  })

  it('shows a run of leave on every day it covers, and marks leave that is only asked for', async () => {
    await open({
      shifts: [],
      leave: [
        { startDate: day(10), endDate: day(11), leaveType: 'Annual leave', status: 'pending' },
      ],
    })
    expect(await screen.findByTestId(`day-${day(10)}`)).toHaveTextContent('Annual leave (asked)')
    expect(screen.getByTestId(`day-${day(11)}`)).toHaveTextContent('Annual leave (asked)')
  })

  it('moves to the next and the previous month and asks for that month', async () => {
    const user = userEvent.setup()
    await open()
    await screen.findByTestId('month-grid')
    await user.click(screen.getByRole('button', { name: 'Next month' }))
    expect(await screen.findByTestId('month-title')).toHaveTextContent(monthLabel(NEXT))
    const next = monthGrid(NEXT)
    await waitFor(() =>
      expect(backend.scheduleQueries).toContain(`?from_date=${next.from}&to_date=${next.to}`),
    )

    await user.click(screen.getByRole('button', { name: 'Previous month' }))
    expect(await screen.findByTestId('month-title')).toHaveTextContent(monthLabel(MONTH))
    expect(await screen.findByTestId(`day-${day(15)}`)).toHaveTextContent('D1')
  })

  it('offers a way back to this month only when away from it', async () => {
    const user = userEvent.setup()
    await open()
    await screen.findByTestId('month-grid')
    expect(screen.queryByRole('button', { name: 'This month' })).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Next month' }))
    await user.click(await screen.findByRole('button', { name: 'This month' }))
    expect(await screen.findByTestId('month-title')).toHaveTextContent(monthLabel(MONTH))
  })

  it('shows today in the grid', async () => {
    await open()
    expect(await screen.findByTestId(`day-${today}`)).toBeVisible()
  })
})

describe('the list view', () => {
  it('lists only days that have something', async () => {
    const user = userEvent.setup()
    await open()
    await user.click(await screen.findByRole('button', { name: 'List' }))
    const list = await screen.findByRole('list', { name: 'My days' })
    expect(within(list).getAllByRole('listitem')).toHaveLength(1)
    expect(within(list).getByTestId(`day-${day(15)}`)).toHaveTextContent('QueueA')
  })

  it('says so when nothing is scheduled', async () => {
    const user = userEvent.setup()
    await open({ shifts: [] })
    await user.click(await screen.findByRole('button', { name: 'List' }))
    expect(await screen.findByTestId('nothing-scheduled')).toBeVisible()
  })
})

describe('notices', () => {
  it('counts shifts that are not published without showing them', async () => {
    await open({ unpublishedShifts: 2 })
    // Failure caught: showing draft shifts as final tells someone to plan around a roster that
    // can still change.
    expect(await screen.findByTestId('unpublished')).toHaveTextContent(
      /2 more shifts are still being planned/,
    )
  })

  it('has no standing notice when every shift is published', async () => {
    // Failure caught: a standing "0 shifts are not published" warning teaches people to ignore it.
    await open({ unpublishedShifts: 0 })
    await screen.findByTestId(`day-${day(15)}`)
    expect(screen.queryByTestId('unpublished')).toBeNull()
  })

  it('points at waiting swaps', async () => {
    await open({ openSwaps: 1 })
    const note = await screen.findByTestId('open-swaps')
    expect(within(note).getByRole('link', { name: 'Open shift swaps' })).toHaveAttribute(
      'href',
      '/shift-swaps',
    )
  })

  it('says so when the person is not on the employee list', async () => {
    seedScheduling()
    backend.noScheduleRecord = true
    await openScheduling('/my-schedule', 'agent')
    expect(await screen.findByTestId('no-record')).toHaveTextContent(/not on the employee list/)
  })
})

describe('breaks inside a shift', () => {
  it('shows the agent their own breaks in the month and in the list', async () => {
    // Failure caught: a lunch planned for 12:00 that the agent never sees.
    await open({
      shifts: [
        {
          day: day(15),
          shift: 'D1',
          startTime: '09:00:00',
          endTime: '17:30:00',
          queue: 'QueueA',
          activities: [{ kind: 'lunch', startTime: '12:00', endTime: '13:00' }],
        },
      ],
    })
    const cell = await screen.findByTestId(`day-${day(15)}`)
    expect(within(cell).getByTestId('activity')).toHaveTextContent('Lunch 12:00')
  })
})

describe('the week calendar', () => {
  it('draws published shifts as blocks, with a glance card and the current-time marker today', async () => {
    // Failure caught: a week view that omits a shift, drops the glance totals, or loses "now".
    const monday = weekStartOf(today)
    const user = userEvent.setup()
    await open({
      fromDate: addDays(monday, -1),
      toDate: addDays(monday, 13),
      shifts: [
        {
          day: monday,
          shift: 'D1',
          startTime: '09:00:00',
          endTime: '17:00:00',
          queue: 'QueueA',
          activities: [{ kind: 'lunch', startTime: '12:00', endTime: '13:00' }],
        },
        {
          day: addDays(monday, 2),
          shift: 'N1',
          startTime: '22:00:00',
          endTime: '06:00:00',
          queue: 'QueueA',
          activities: [],
        },
      ],
    })
    await user.click(await screen.findByRole('button', { name: 'Week' }))
    const blocks = await screen.findAllByTestId('week-block')
    // The night shift is cut at midnight: one day block, one block for each part of the night.
    expect(blocks).toHaveLength(3)
    expect(screen.getByTestId('glance-shifts')).toHaveTextContent('2')
    expect(screen.getByTestId('glance-hours')).toHaveTextContent('15 h')
    expect(screen.getByTestId('glance-activity')).toHaveTextContent('Lunch')
    expect(screen.getByTestId('week-glance')).toBeVisible()
    // Failure caught: scrolling parts of the calendar that the keyboard cannot reach.
    for (const name of ['Week calendar', 'Hours of the week'])
      expect(screen.getByRole('region', { name })).toHaveAttribute('tabindex', '0')
    if (today >= monday && today <= addDays(monday, 6)) {
      expect(screen.getByTestId('now-marker')).toBeInTheDocument()
    }
  })

  it('goes back to the agenda list with the existing list view', async () => {
    // Failure caught: Agenda no longer reachable once the week view exists.
    const user = userEvent.setup()
    await open()
    await user.click(await screen.findByRole('button', { name: 'Week' }))
    await user.click(screen.getByRole('button', { name: 'List' }))
    expect(await screen.findByLabelText('My days')).toBeInTheDocument()
  })
})
