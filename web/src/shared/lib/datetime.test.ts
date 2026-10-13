import { describe, expect, it } from 'vitest'

import { dayOf, formatDate, formatDateTime, formatDayLabel, timeOf } from './datetime'

describe('South African time', () => {
  it('shows the next day for a UTC time after 22:00 (SAST is UTC+2)', () => {
    // A call at 00:30 on 5 May in Johannesburg is 22:30 on 4 May in UTC.
    expect(formatDate('2026-05-04T22:30:00Z')).toMatch(/^0?5 May/)
    expect(formatDate('2026-05-04T22:30:00Z')).toMatch(/May/)
    expect(formatDateTime('2026-05-04T22:30:00Z')).toMatch(/00:30/)
  })

  it('keeps the same day earlier in the evening', () => {
    expect(formatDateTime('2026-05-04T19:59:00Z')).toMatch(/21:59/)
    expect(formatDate('2026-05-04T19:59:00Z')).toMatch(/^0?4 May/)
  })
})

describe('dayOf and timeOf', () => {
  it('name the South African day and clock time, not the UTC ones', () => {
    // 22:00 UTC on 4 May is midnight, the start of 5 May, in Johannesburg.
    expect(dayOf('2026-05-04T22:00:00Z')).toBe('2026-05-05')
    expect(timeOf('2026-05-04T22:00:00Z')).toBe('00:00')
    expect(dayOf('2026-05-04T21:59:00Z')).toBe('2026-05-04')
    expect(timeOf('2026-05-25T08:00:00Z')).toBe('10:00')
    expect(timeOf('2026-05-25T08:30:00Z')).toBe('10:30')
  })
})

describe('formatDayLabel', () => {
  it('names a plain day without ever moving it to a neighbouring day', () => {
    expect(formatDayLabel('2026-05-25')).toMatch(/Mon.*25.*May/)
    expect(formatDayLabel('2026-05-01')).toMatch(/Fri.*1.*May/)
    expect(formatDayLabel('2026-12-31')).toMatch(/Thu.*31.*Dec/)
  })
})
