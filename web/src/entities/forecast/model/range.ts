/** Calendar arithmetic and colouring for the week and month views. Days are plain `YYYY-MM-DD`
 * strings and the maths is done in UTC, so no time zone can move a day. */

export type ForecastView = 'day' | 'week' | 'month'

const DAY_MS = 86_400_000

const at = (day: string): Date => new Date(`${day}T00:00:00Z`)
const iso = (date: Date): string => date.toISOString().slice(0, 10)

export function addDays(day: string, n: number): string {
  return iso(new Date(at(day).getTime() + n * DAY_MS))
}

/** The Monday on or before `day` (weeks run Monday to Sunday). */
export function mondayOf(day: string): string {
  const weekday = (at(day).getUTCDay() + 6) % 7 // Monday = 0
  return addDays(day, -weekday)
}

export function weekOf(day: string): string[] {
  const monday = mondayOf(day)
  return Array.from({ length: 7 }, (_, n) => addDays(monday, n))
}

export interface MonthGrid {
  month: string // "2026-05"
  days: string[] // whole Monday-to-Sunday weeks covering the month: 28 to 42 days
}

export function monthOf(day: string): MonthGrid {
  const month = day.slice(0, 7)
  const first = `${month}-01`
  const next = new Date(Date.UTC(Number(month.slice(0, 4)), Number(month.slice(5, 7)), 1))
  const last = addDays(iso(next), -1)
  const start = mondayOf(first)
  const end = addDays(mondayOf(last), 6)
  const length = (at(end).getTime() - at(start).getTime()) / DAY_MS + 1
  return { month, days: Array.from({ length }, (_, n) => addDays(start, n)) }
}

/** The same day-of-month in the next (or previous) month, or its last day if that is shorter. */
export function shiftMonth(day: string, by: number): string {
  const year = Number(day.slice(0, 4))
  const month = Number(day.slice(5, 7)) - 1 + by
  const lastDay = new Date(Date.UTC(year, month + 1, 0)).getUTCDate()
  return iso(new Date(Date.UTC(year, month, Math.min(Number(day.slice(8, 10)), lastDay))))
}

/** The first and last day to ask the server for: the week, or the whole month grid. */
export function rangeFor(view: ForecastView, anchor: string): { from: string; to: string } {
  if (view === 'month') {
    const { days } = monthOf(anchor)
    return { from: days[0] as string, to: days[days.length - 1] as string }
  }
  const week = weekOf(anchor)
  return { from: week[0] as string, to: week[6] as string }
}

/** The anchor moved on (or back) by one week or one month. */
export function step(view: ForecastView, anchor: string, direction: 1 | -1): string {
  return view === 'month' ? shiftMonth(anchor, direction) : addDays(anchor, 7 * direction)
}

/** How strong a heat-grid cell is, 0 to 1. A cell with nobody needed is the faintest, the busiest
 * cell of the week is full strength; an unknown cell has no strength (it is drawn differently). */
export function heat(required: number | null, max: number): number | null {
  if (required === null) return null
  if (max <= 0) return 0
  return Math.min(1, Math.max(0, required / max))
}

/** "10:00" for half-hour 20. */
export function slotLabel(slot: number): string {
  const hh = String(Math.floor(slot / 2)).padStart(2, '0')
  return `${hh}:${slot % 2 === 0 ? '00' : '30'}`
}
