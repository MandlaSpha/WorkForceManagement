import { screen, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { MySchedule } from '@/entities/my-schedule'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

const schedule = (over: Partial<MySchedule> = {}): MySchedule => ({
  employee: 'Alex Agent',
  fromDate: '2099-06-01',
  toDate: '2099-06-28',
  shifts: [
    { day: '2099-06-01', shift: 'D1', startTime: '09:00:00', endTime: '17:30:00', queue: 'QueueA' },
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

describe('my schedule', () => {
  it('shows each published shift with its times and queue', async () => {
    await open()
    const day = await screen.findByTestId('day-2099-06-01')
    expect(day).toHaveTextContent('D1')
    expect(day).toHaveTextContent('09:00-17:30')
    expect(day).toHaveTextContent('QueueA')
  })

  it('shows a run of leave on every day it covers, and says when it is only asked for', async () => {
    await open({
      shifts: [],
      leave: [
        {
          startDate: '2099-06-02',
          endDate: '2099-06-03',
          leaveType: 'Annual leave',
          status: 'pending',
        },
      ],
    })
    expect(await screen.findByTestId('day-2099-06-02')).toHaveTextContent('waiting for a decision')
    expect(screen.getByTestId('day-2099-06-03')).toHaveTextContent('Annual leave')
  })

  it('counts shifts that are not published without showing them', async () => {
    await open({ unpublishedShifts: 2 })
    // Failure caught: showing draft shifts as final tells someone to plan around a roster that
    // can still change.
    expect(await screen.findByTestId('unpublished')).toHaveTextContent(/2 shifts are not published/)
  })

  it('points at waiting swaps', async () => {
    await open({ openSwaps: 1 })
    const note = await screen.findByTestId('open-swaps')
    expect(within(note).getByRole('link', { name: 'Open shift swaps' })).toHaveAttribute(
      'href',
      '/shift-swaps',
    )
  })

  it('says so when nothing is scheduled', async () => {
    await open({ shifts: [] })
    expect(await screen.findByTestId('nothing-scheduled')).toBeVisible()
  })

  it('says so when the person is not on the employee list', async () => {
    seedScheduling()
    backend.noScheduleRecord = true
    await openScheduling('/my-schedule', 'agent')
    expect(await screen.findByTestId('no-record')).toHaveTextContent(/not on the employee list/)
  })
})
