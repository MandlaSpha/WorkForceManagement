import { describe, expect, it } from 'vitest'

import { formatMinutes } from './duration'

describe('formatMinutes', () => {
  it('writes whole hours, hours and minutes, and minutes alone', () => {
    expect(formatMinutes(480)).toBe('8h')
    expect(formatMinutes(450)).toBe('7h 30m')
    expect(formatMinutes(45)).toBe('45m')
    expect(formatMinutes(24408)).toBe('406h 48m')
  })

  it('shows nothing as 0m and rounds a fraction of a minute', () => {
    expect(formatMinutes(0)).toBe('0m')
    expect(formatMinutes(59.6)).toBe('1h')
    expect(formatMinutes(0.4)).toBe('0m')
  })
})
