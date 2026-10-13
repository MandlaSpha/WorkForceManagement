/** Calendar months as `YYYY-MM` strings. Plain string maths: no Date, so no time-zone surprises. */

const MONTH = /^(\d{4})-(0[1-9]|1[0-2])$/

function parts(month: string): [number, number] {
  const match = MONTH.exec(month)
  if (!match) throw new Error(`Not a month: ${month}`)
  return [Number(match[1]), Number(match[2])]
}

function daysIn(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate()
}

/** First and last day of a month, as ISO dates: `2026-02` gives 2026-02-01 and 2026-02-28. */
export function monthRange(month: string): { from: string; to: string } {
  const [year, number] = parts(month)
  return { from: `${month}-01`, to: `${month}-${String(daysIn(year, number)).padStart(2, '0')}` }
}

const NAMES = [
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

export function formatMonth(month: string): string {
  const [year, number] = parts(month)
  return `${NAMES[number - 1]} ${year}`
}
