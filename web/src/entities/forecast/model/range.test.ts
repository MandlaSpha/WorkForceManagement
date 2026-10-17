import { describe, expect, it } from 'vitest'

import {
  addDays,
  heat,
  mondayOf,
  monthOf,
  rangeFor,
  shiftMonth,
  slotLabel,
  step,
  weekOf,
} from './range'

describe('weeks', () => {
  it('run Monday to Sunday and a Sunday belongs to the week before the next Monday', () => {
    // Failure caught: a Sunday-first week, which would put 31 May in the week of Monday 1 June.
    expect(mondayOf('2026-05-31')).toBe('2026-05-25')
    expect(mondayOf('2026-05-25')).toBe('2026-05-25')
    expect(weekOf('2026-05-27')).toEqual([
      '2026-05-25',
      '2026-05-26',
      '2026-05-27',
      '2026-05-28',
      '2026-05-29',
      '2026-05-30',
      '2026-05-31',
    ])
  })

  it('cross a month and a year end without slipping a day', () => {
    // Failure caught: local-time maths moving a day across a clock change.
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01')
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28')
    expect(weekOf('2026-12-31')[6]).toBe('2027-01-03')
  })
})

describe('months', () => {
  it('cover whole weeks, Monday first', () => {
    const grid = monthOf('2026-05-12') // 1 May is a Friday; 31 May a Sunday
    expect(grid.days[0]).toBe('2026-04-27')
    expect(grid.days[grid.days.length - 1]).toBe('2026-05-31')
    expect(grid.days).toHaveLength(35)
  })

  it('can need six weeks', () => {
    // Failure caught: a grid cut at five rows, hiding 31 August 2026.
    expect(monthOf('2026-08-15').days).toHaveLength(42)
  })

  it('can fit four weeks exactly', () => {
    expect(monthOf('2027-02-10').days).toHaveLength(28) // 1 Feb 2027 is a Monday
  })

  it('moves by a month and keeps to the end of a shorter month', () => {
    // Failure caught: 31 Jan + 1 month becoming 3 March.
    expect(shiftMonth('2026-01-31', 1)).toBe('2026-02-28')
    expect(shiftMonth('2026-01-15', -1)).toBe('2025-12-15')
  })
})

describe('the range to ask for', () => {
  it('is the week, or the whole month grid', () => {
    expect(rangeFor('week', '2026-05-27')).toEqual({ from: '2026-05-25', to: '2026-05-31' })
    expect(rangeFor('month', '2026-05-27')).toEqual({ from: '2026-04-27', to: '2026-05-31' })
  })

  it('steps a week or a month', () => {
    expect(step('week', '2026-05-27', 1)).toBe('2026-06-03')
    expect(step('month', '2026-05-27', -1)).toBe('2026-04-27')
  })
})

describe('heat', () => {
  it('scales to the busiest cell and keeps unknown apart from zero', () => {
    // Failure caught: an unknown requirement drawn as the faintest "nobody needed" cell.
    expect(heat(6, 6)).toBe(1)
    expect(heat(3, 6)).toBe(0.5)
    expect(heat(0, 6)).toBe(0)
    expect(heat(null, 6)).toBeNull()
    expect(heat(0, 0)).toBe(0)
  })
})

it('labels half-hours', () => {
  expect([slotLabel(0), slotLabel(1), slotLabel(20), slotLabel(47)]).toEqual([
    '00:00',
    '00:30',
    '10:00',
    '23:30',
  ])
})
