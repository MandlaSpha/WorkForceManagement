import { describe, expect, it } from 'vitest'

import { monthGrid, monthLabel, monthOf, shiftMonth } from './month'

describe('month grid', () => {
  it('covers whole Monday-to-Sunday weeks around the month', () => {
    // October 2026 starts on a Thursday and ends on a Saturday.
    const grid = monthGrid('2026-10')
    expect(grid.from).toBe('2026-09-28')
    expect(grid.to).toBe('2026-11-01')
    expect(grid.weeks).toHaveLength(5)
    expect(grid.weeks[0]?.[0]).toBe('2026-09-28')
    expect(grid.weeks[4]?.[6]).toBe('2026-11-01')
  })

  it('needs only four rows for a February that starts on a Monday', () => {
    // February 2027 starts on a Monday and has 28 days.
    const grid = monthGrid('2027-02')
    expect(grid.weeks).toHaveLength(4)
    expect(grid.from).toBe('2027-02-01')
    expect(grid.to).toBe('2027-02-28')
  })

  it('can need six rows, still inside the 62 days the API allows', () => {
    // August 2026 starts on a Saturday and has 31 days: Mon 27 Jul to Sun 6 Sep.
    const grid = monthGrid('2026-08')
    expect(grid.weeks).toHaveLength(6)
    const days = grid.weeks.flat().length
    expect(days).toBe(42)
    expect(days).toBeLessThanOrEqual(62)
  })

  it('every week has seven days, Monday first, and no day repeats', () => {
    const all = monthGrid('2026-12').weeks.flat()
    expect(new Set(all).size).toBe(all.length)
    for (const week of monthGrid('2026-12').weeks) expect(week).toHaveLength(7)
  })
})

describe('months', () => {
  it('moves across a year end in both directions', () => {
    expect(shiftMonth('2026-12', 1)).toBe('2027-01')
    expect(shiftMonth('2027-01', -1)).toBe('2026-12')
    expect(shiftMonth('2026-03', 0)).toBe('2026-03')
    expect(shiftMonth('2026-03', 13)).toBe('2027-04')
  })

  it('names a month and finds the month of a date', () => {
    expect(monthLabel('2026-10')).toBe('October 2026')
    expect(monthOf('2026-10-14')).toBe('2026-10')
  })
})
