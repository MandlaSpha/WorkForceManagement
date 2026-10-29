import { addDays } from '@/shared/lib/week'

import type { MyShift } from './types'

export const DAY_MINUTES = 1440

/** "09:30" or "09:30:00" as minutes since midnight. */
export function minutesOf(time: string): number {
  const [h, m] = time.split(':').map(Number)
  return (h ?? 0) * 60 + (m ?? 0)
}

/** One drawn block: a shift, or the part of an overnight shift that falls on one calendar day. */
export interface Segment {
  day: string
  startMin: number
  endMin: number
  shift: MyShift
  /** True for the part after midnight of a shift that began the day before. */
  continued: boolean
}

/** A shift whose end is not after its start runs past midnight, so it is cut at midnight into
 * a part on its own day and a part on the next. */
export function shiftSegments(shift: MyShift): Segment[] {
  const start = minutesOf(shift.startTime)
  const end = minutesOf(shift.endTime)
  if (end > start) {
    return [{ day: shift.day, startMin: start, endMin: end, shift, continued: false }]
  }
  const parts: Segment[] = [
    { day: shift.day, startMin: start, endMin: DAY_MINUTES, shift, continued: false },
  ]
  if (end > 0) {
    parts.push({ day: addDays(shift.day, 1), startMin: 0, endMin: end, shift, continued: true })
  }
  return parts
}

/** The blocks that fall inside the seven days from `weekStart`. Pass shifts fetched from the day
 * before so a Sunday-night shift still shows its early-Monday tail. */
export function weekSegments(shifts: MyShift[], weekStart: string): Segment[] {
  const last = addDays(weekStart, 6)
  return shifts
    .flatMap(shiftSegments)
    .filter((s) => s.day >= weekStart && s.day <= last)
    .sort((a, b) => a.day.localeCompare(b.day) || a.startMin - b.startMin)
}

/** Top and height as percentages of the 24-hour axis. */
export function positionOf(startMin: number, endMin: number): { top: number; height: number } {
  return {
    top: (startMin / DAY_MINUTES) * 100,
    height: ((endMin - startMin) / DAY_MINUTES) * 100,
  }
}

export interface Placed<T> {
  item: T
  column: number
  columns: number
}

/** Side-by-side columns for blocks that overlap in time: each block takes the first free column,
 * and every block in an overlapping cluster shares the cluster's column count. */
export function overlapColumns<T extends { startMin: number; endMin: number }>(
  items: T[],
): Placed<T>[] {
  const sorted = [...items].sort((a, b) => a.startMin - b.startMin || a.endMin - b.endMin)
  const placed: Placed<T>[] = []
  let cluster: Placed<T>[] = []
  let clusterEnd = -1
  let ends: number[] = []
  const flush = () => {
    for (const p of cluster) p.columns = Math.max(1, ends.length)
    cluster = []
    ends = []
  }
  for (const item of sorted) {
    if (item.startMin >= clusterEnd) flush()
    let column = ends.findIndex((e) => e <= item.startMin)
    if (column < 0) column = ends.length
    ends[column] = item.endMin
    clusterEnd = cluster.length === 0 ? item.endMin : Math.max(clusterEnd, item.endMin)
    const p = { item, column, columns: 1 }
    cluster.push(p)
    placed.push(p)
  }
  flush()
  return placed
}

function lengthMinutes(start: string, end: string): number {
  const s = minutesOf(start)
  const e = minutesOf(end)
  return e > s ? e - s : e + DAY_MINUTES - s
}

/** Hours worked: the shift's length minus lunches (unpaid), counted once for the whole shift. */
export function paidHours(shift: MyShift): number {
  let minutes = lengthMinutes(shift.startTime, shift.endTime)
  for (const a of shift.activities) {
    if (a.kind === 'lunch') minutes -= lengthMinutes(a.startTime, a.endTime)
  }
  return Math.max(0, minutes) / 60
}

export type ShiftKind = 'early' | 'day' | 'late' | 'night'

/** Early, day, late or night, from when the shift starts; the data carries no kind of its own. */
export function shiftKind(shift: MyShift): ShiftKind {
  const start = minutesOf(shift.startTime)
  const end = minutesOf(shift.endTime)
  if (end <= start || start >= 21 * 60 || start < 4 * 60) return 'night'
  if (start < 8 * 60) return 'early'
  if (start >= 13 * 60) return 'late'
  return 'day'
}

export interface WeekSummary {
  shifts: number
  paidHours: number
  /** Minutes by activity kind, biggest first. */
  activityMinutes: { kind: string; minutes: number }[]
}

export function summarise(shifts: MyShift[]): WeekSummary {
  const by = new Map<string, number>()
  let hours = 0
  for (const s of shifts) {
    hours += paidHours(s)
    for (const a of s.activities) {
      by.set(a.kind, (by.get(a.kind) ?? 0) + lengthMinutes(a.startTime, a.endTime))
    }
  }
  return {
    shifts: shifts.length,
    paidHours: hours,
    activityMinutes: [...by.entries()]
      .map(([kind, minutes]) => ({ kind, minutes }))
      .sort((a, b) => b.minutes - a.minutes),
  }
}

/** The next `count` shifts that have not ended yet, soonest first. */
export function upNext(shifts: MyShift[], today: string, nowMin: number, count = 3): MyShift[] {
  return shifts
    .filter((s) => {
      const end = minutesOf(s.endTime)
      const overnight = end <= minutesOf(s.startTime)
      if (s.day > today) return true
      if (s.day === today) return overnight || end > nowMin
      return overnight && addDays(s.day, 1) === today && end > nowMin
    })
    .sort((a, b) => a.day.localeCompare(b.day) || a.startTime.localeCompare(b.startTime))
    .slice(0, count)
}

/** Hours with one decimal, dropping a trailing ".0": 38 h, 7.5 h. */
export function hoursLabel(hours: number): string {
  return `${Number(hours.toFixed(1))} h`
}
