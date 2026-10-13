import { describe, expect, it } from 'vitest'

import { formatDate, formatDateTime } from './datetime'

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
