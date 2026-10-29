import { describe, expect, it } from 'vitest'

import {
  dayOf,
  formatDate,
  formatDateTime,
  formatDayLabel,
  greeting,
  relativeTime,
  longDay,
  partOfDay,
  timeOf,
} from './datetime'

describe('greeting', () => {
  it('uses South African time, not the browser or UTC', () => {
    // 22:30 UTC on the 28th is 00:30 on the 29th in Johannesburg.
    // Failure caught: greeting by UTC hour ("Good evening" in the middle of the night here).
    expect(partOfDay(new Date('2026-10-28T22:30:00Z'))).toBe('morning')
    expect(partOfDay(new Date('2026-10-29T09:59:00Z'))).toBe('morning') // 11:59
    expect(partOfDay(new Date('2026-10-29T10:00:00Z'))).toBe('afternoon') // 12:00
    expect(partOfDay(new Date('2026-10-29T16:00:00Z'))).toBe('evening') // 18:00
  })

  it('uses only the first word of the name', () => {
    expect(greeting(new Date('2026-10-29T07:00:00Z'), 'Thandi Mokoena')).toBe(
      'Good morning, Thandi',
    )
  })

  it('shows no dangling comma when there is no name', () => {
    expect(greeting(new Date('2026-10-29T07:00:00Z'), '  ')).toBe('Good morning')
    expect(greeting(new Date('2026-10-29T07:00:00Z'), undefined)).toBe('Good morning')
  })

  it('writes the long date in South African time', () => {
    expect(longDay(new Date('2026-10-29T07:00:00Z'))).toMatch(/Thursday.*29.*October/)
  })
})

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

const now = new Date('2026-05-20T12:00:00Z')

describe('relativeTime', () => {
  it('says how long ago in the unit a person would use', () => {
    // Failure caught: "0 min ago" or "1440 min ago" instead of plain words.
    expect(relativeTime('2026-05-20T11:59:50Z', now)).toBe('just now')
    expect(relativeTime('2026-05-20T11:55:00Z', now)).toBe('5 min ago')
    expect(relativeTime('2026-05-20T09:00:00Z', now)).toBe('3 h ago')
    expect(relativeTime('2026-05-18T12:00:00Z', now)).toBe('2 d ago')
  })

  it('falls back to a date after a week, and never throws on a bad value', () => {
    expect(relativeTime('2026-04-01T12:00:00Z', now)).toMatch(/1/)
    expect(relativeTime('nonsense', now)).toBe('just now')
  })
})
