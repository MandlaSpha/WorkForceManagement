import { describe, expect, it } from 'vitest'

import type { MyShift } from './types'
import {
  overlapColumns,
  paidHours,
  positionOf,
  shiftKind,
  shiftSegments,
  summarise,
  upNext,
  weekSegments,
} from './week'

const shift = (over: Partial<MyShift> = {}): MyShift => ({
  day: '2026-10-26',
  shift: 'D1',
  startTime: '09:00:00',
  endTime: '17:30:00',
  queue: 'Q',
  activities: [],
  ...over,
})
const NIGHT = { startTime: '22:00:00', endTime: '06:00:00' }

describe('shiftSegments', () => {
  it('keeps a day shift as one block', () => {
    // Failure caught: a normal shift drawn twice or cut.
    expect(shiftSegments(shift())).toHaveLength(1)
  })
  it('splits an overnight shift at midnight onto the next day', () => {
    // Failure caught: a night shift drawn upside down or running off the bottom of the grid.
    const parts = shiftSegments(shift({ day: '2026-10-31', ...NIGHT }))
    expect(parts.map((p) => [p.day, p.startMin, p.endMin, p.continued])).toEqual([
      ['2026-10-31', 1320, 1440, false],
      ['2026-11-01', 0, 360, true],
    ])
  })
})

describe('weekSegments', () => {
  it('shows the Monday tail of a Sunday night shift and drops days outside the week', () => {
    // Failure caught: the early hours of Monday looking free, or next week's shifts leaking in.
    const sundayNight = shift({ day: '2026-10-25', ...NIGHT })
    const nextWeek = shift({ day: '2026-11-02' })
    const segs = weekSegments([sundayNight, nextWeek], '2026-10-26')
    expect(segs.map((s) => [s.day, s.startMin, s.endMin])).toEqual([['2026-10-26', 0, 360]])
  })
})

describe('positionOf', () => {
  it('maps minutes to a percentage of 24 hours', () => {
    // Failure caught: blocks placed on a 12-hour or pixel scale.
    expect(positionOf(360, 720)).toEqual({ top: 25, height: 25 })
  })
})

describe('overlapColumns', () => {
  it('puts overlapping blocks side by side and lets later blocks reuse a free column', () => {
    // Failure caught: overlapping blocks drawn on top of each other.
    const out = overlapColumns([
      { startMin: 0, endMin: 120 },
      { startMin: 60, endMin: 180 },
      { startMin: 130, endMin: 200 },
      { startMin: 400, endMin: 500 },
    ])
    expect(out.map((p) => [p.column, p.columns])).toEqual([
      [0, 2],
      [1, 2],
      [0, 2],
      [0, 1],
    ])
  })
})

describe('paidHours', () => {
  it('takes lunch off and counts an overnight shift whole', () => {
    // Failure caught: an unpaid lunch counted as work, or a night shift counted as negative.
    const lunch = [{ kind: 'lunch', startTime: '12:00', endTime: '12:30' }]
    expect(paidHours(shift({ activities: lunch }))).toBe(8)
    expect(paidHours(shift(NIGHT))).toBe(8)
  })
})

describe('shiftKind', () => {
  it('names shifts by when they start', () => {
    // Failure caught: every shift the same colour.
    expect(shiftKind(shift({ startTime: '06:00:00' }))).toBe('early')
    expect(shiftKind(shift())).toBe('day')
    expect(shiftKind(shift({ startTime: '14:00:00', endTime: '22:00:00' }))).toBe('late')
    expect(shiftKind(shift(NIGHT))).toBe('night')
  })
})

describe('summarise and upNext', () => {
  it('totals hours and activity minutes', () => {
    // Failure caught: the glance card disagreeing with the grid.
    const a = [{ kind: 'break', startTime: '10:00', endTime: '10:15' }]
    const s = summarise([shift({ activities: a }), shift({ activities: a })])
    expect(s.shifts).toBe(2)
    expect(s.activityMinutes).toEqual([{ kind: 'break', minutes: 30 }])
  })
  it('lists the next three shifts that have not ended', () => {
    // Failure caught: finished shifts listed as "up next".
    const list = [
      shift({ day: '2026-10-26' }),
      shift({ day: '2026-10-27', shift: 'B' }),
      shift({ day: '2026-10-28', shift: 'C' }),
      shift({ day: '2026-10-29', shift: 'D' }),
    ]
    expect(upNext(list, '2026-10-27', 20 * 60).map((s) => s.shift)).toEqual(['C', 'D'])
    expect(upNext(list, '2026-10-27', 8 * 60).map((s) => s.shift)).toEqual(['B', 'C', 'D'])
  })
})
