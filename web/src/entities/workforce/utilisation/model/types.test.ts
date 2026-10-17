import { describe, expect, it } from 'vitest'

import { gapLabel, hours, pct, rands } from './types'

describe('utilisation formatting', () => {
  it('shows a missing percentage as a dash, never 0%', () => {
    expect(pct(null)).toBe('-')
    expect(pct(undefined)).toBe('-')
    expect(pct(0)).toBe('0.0%')
    expect(pct(81.25)).toBe('81.3%')
  })

  it('signs the gap in percentage points', () => {
    expect(gapLabel(5)).toBe('+5.0 pts')
    expect(gapLabel(-12.5)).toBe('-12.5 pts')
    expect(gapLabel(0)).toBe('0.0 pts')
    expect(gapLabel(null)).toBe('-')
  })

  it('shows rands with grouping and cents, and a dash for unknown', () => {
    expect(rands(1223.1)).toBe('R1 223.10')
    expect(rands(1234567.5)).toBe('R1 234 567.50')
    expect(rands(-50)).toBe('-R50.00')
    expect(rands(0)).toBe('R0.00')
    expect(rands(null)).toBe('-')
  })

  it('turns minutes into hours', () => {
    expect(hours(90)).toBe('1.5')
  })
})
