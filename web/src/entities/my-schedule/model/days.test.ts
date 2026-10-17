import { describe, expect, it } from 'vitest'

import { daysWithSomething } from './days'

const shift = (day: string, code = 'D1') => ({
  day,
  shift: code,
  startTime: '09:00:00',
  endTime: '17:30:00',
  queue: 'QueueA',
  activities: [],
})
const leave = (startDate: string, endDate: string, status = 'approved') => ({
  startDate,
  endDate,
  leaveType: 'Annual leave',
  status,
})

describe('daysWithSomething', () => {
  it('lists only days that have a shift or leave, in date order', () => {
    const days = daysWithSomething(
      [shift('2026-06-03'), shift('2026-06-01')],
      [],
      '2026-06-01',
      '2026-06-07',
    )
    expect(days.map((d) => d.day)).toEqual(['2026-06-01', '2026-06-03'])
  })

  it('spreads a run of leave over every day it covers, not just the first', () => {
    // Failure caught: showing only the first day makes three days of leave look like one.
    const days = daysWithSomething(
      [],
      [leave('2026-06-02', '2026-06-04')],
      '2026-06-01',
      '2026-06-07',
    )
    expect(days.map((d) => d.day)).toEqual(['2026-06-02', '2026-06-03', '2026-06-04'])
  })

  it('cuts leave that starts before or runs past the window to the window', () => {
    const days = daysWithSomething(
      [],
      [leave('2026-05-29', '2026-06-10')],
      '2026-06-01',
      '2026-06-03',
    )
    expect(days.map((d) => d.day)).toEqual(['2026-06-01', '2026-06-02', '2026-06-03'])
  })

  it('puts a shift and leave on the same day together', () => {
    const days = daysWithSomething(
      [shift('2026-06-02')],
      [leave('2026-06-02', '2026-06-02', 'pending')],
      '2026-06-01',
      '2026-06-07',
    )
    expect(days).toHaveLength(1)
    expect(days[0]?.shifts).toHaveLength(1)
    expect(days[0]?.leave[0]?.status).toBe('pending')
  })

  it('is empty when there is nothing', () => {
    expect(daysWithSomething([], [], '2026-06-01', '2026-06-07')).toEqual([])
  })
})
