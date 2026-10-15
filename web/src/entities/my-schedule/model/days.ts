import type { MyLeave, MyShift } from './types'

export interface ScheduleDay {
  day: string
  shifts: MyShift[]
  leave: MyLeave[]
}

/** Only the days that have a shift or leave, in date order. Leave covers every day it spans, so a
 * week of leave shows as a week, not as its first day. */
export function daysWithSomething(
  shifts: MyShift[],
  leave: MyLeave[],
  from: string,
  to: string,
): ScheduleDay[] {
  const days = new Map<string, ScheduleDay>()
  const entry = (day: string): ScheduleDay => {
    let found = days.get(day)
    if (!found) {
      found = { day, shifts: [], leave: [] }
      days.set(day, found)
    }
    return found
  }
  for (const s of shifts) entry(s.day).shifts.push(s)
  for (const l of leave) {
    for (let t = Date.parse(`${l.startDate}T00:00:00Z`); ; t += 86_400_000) {
      const day = new Date(t).toISOString().slice(0, 10)
      if (day > l.endDate) break
      if (day >= from && day <= to) entry(day).leave.push(l)
    }
  }
  return [...days.values()].sort((a, b) => a.day.localeCompare(b.day))
}
