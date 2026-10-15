import { addDays, weekStartOf } from '@/shared/lib/week'

const MONTH_NAMES = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
]

/** "2026-10" for any ISO date in October 2026. */
export function monthOf(iso: string): string {
  return iso.slice(0, 7)
}

export function monthLabel(month: string): string {
  const [year, number] = month.split('-').map(Number)
  return `${MONTH_NAMES[(number ?? 1) - 1]} ${year}`
}

/** The month `delta` months away ("2026-12" + 1 is "2027-01"). */
export function shiftMonth(month: string, delta: number): string {
  const [year, number] = month.split('-').map(Number)
  const index = (year ?? 1970) * 12 + ((number ?? 1) - 1) + delta
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, '0')}`
}

export interface MonthGrid {
  /** The Monday the grid starts on (it may be in the month before). */
  from: string
  /** The Sunday it ends on (it may be in the month after). */
  to: string
  /** Weeks of seven ISO dates, Monday first. */
  weeks: string[][]
}

/** Whole weeks, Monday to Sunday, covering every day of `month`: 4 to 6 rows. A month is at most
 * 42 days on the grid, inside the 62 days the schedule can be asked for. */
export function monthGrid(month: string): MonthGrid {
  const first = `${month}-01`
  const lastDay = addDays(`${shiftMonth(month, 1)}-01`, -1)
  const from = weekStartOf(first)
  const to = addDays(weekStartOf(lastDay), 6)
  const weeks: string[][] = []
  for (let monday = from; monday <= to; monday = addDays(monday, 7)) {
    weeks.push(Array.from({ length: 7 }, (_, n) => addDays(monday, n)))
  }
  return { from, to, weeks }
}
