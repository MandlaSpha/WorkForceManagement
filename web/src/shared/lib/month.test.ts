import { describe, expect, it } from 'vitest'

import { formatMonth, monthRange } from './month'

describe('monthRange', () => {
  it.each([
    ['2026-05', '2026-05-01', '2026-05-31'],
    ['2026-06', '2026-06-01', '2026-06-30'],
    ['2026-02', '2026-02-01', '2026-02-28'],
    ['2028-02', '2028-02-01', '2028-02-29'], // leap year
    ['2100-02', '2100-02-01', '2100-02-28'], // 2100 is not a leap year
    ['2026-12', '2026-12-01', '2026-12-31'],
  ])('%s runs from the 1st to its real last day', (month, from, to) => {
    expect(monthRange(month)).toEqual({ from, to })
  })

  it('refuses something that is not a month instead of guessing', () => {
    expect(() => monthRange('2026-13')).toThrow()
    expect(() => monthRange('May')).toThrow()
  })
})

describe('formatMonth', () => {
  it('names the month for people', () => {
    expect(formatMonth('2026-07')).toBe('July 2026')
  })
})
