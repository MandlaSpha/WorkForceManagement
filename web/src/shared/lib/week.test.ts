import { describe, expect, it } from 'vitest'

import { addDays, addWeeks, formatWeekRange, todayInJohannesburg, weekStartOf } from './week'

describe('weekStartOf', () => {
  it('returns the Monday of the week', () => {
    expect(weekStartOf('2026-08-19')).toBe('2026-08-17') // Wednesday
    expect(weekStartOf('2026-08-17')).toBe('2026-08-17') // Monday itself
  })

  it('treats Sunday as the end of the week, not the start', () => {
    expect(weekStartOf('2026-08-23')).toBe('2026-08-17')
  })

  it('crosses month and year boundaries', () => {
    expect(weekStartOf('2027-01-01')).toBe('2026-12-28')
  })
})

describe('addDays / addWeeks', () => {
  it('moves by whole days across a leap day', () => {
    expect(addDays('2028-02-28', 2)).toBe('2028-03-01')
  })

  it('moves by weeks and snaps to Monday', () => {
    expect(addWeeks('2026-08-19', 1)).toBe('2026-08-24')
    expect(addWeeks('2026-08-19', -2)).toBe('2026-08-03')
  })
})

describe('formatWeekRange', () => {
  it('formats a week inside one month', () => {
    expect(formatWeekRange('2026-08-17')).toBe('17 Aug – 23 Aug')
  })

  it('formats a week spanning two months', () => {
    expect(formatWeekRange('2026-08-31')).toBe('31 Aug – 6 Sep')
  })
})

describe('validation', () => {
  it.each(['2026-02-30', '2026-13-01', 'tomorrow', '2026-8-1'])('rejects %s', (bad) => {
    expect(() => weekStartOf(bad)).toThrow()
  })
})

describe('todayInJohannesburg', () => {
  it('uses South African time, not the machine time', () => {
    // 22:30 UTC on 17 Aug is already 00:30 on 18 Aug in Johannesburg (UTC+2).
    expect(todayInJohannesburg(new Date('2026-08-17T22:30:00Z'))).toBe('2026-08-18')
    expect(todayInJohannesburg(new Date('2026-08-17T12:00:00Z'))).toBe('2026-08-17')
  })
})
