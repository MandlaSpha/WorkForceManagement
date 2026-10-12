/**
 * Week helpers on plain ISO dates (YYYY-MM-DD). Everything is done in UTC on the date alone so a
 * viewer's own time zone can never shift a roster week. Weeks start on Monday (South African
 * convention, matches the reference UI).
 */

const DAY_MS = 86_400_000
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

function parse(iso: string): Date {
  if (!ISO_DATE.test(iso)) throw new Error(`Not an ISO date: ${iso}`)
  const [y, m, d] = iso.split('-').map(Number) as [number, number, number]
  const date = new Date(Date.UTC(y, m - 1, d))
  if (date.getUTCFullYear() !== y || date.getUTCMonth() !== m - 1 || date.getUTCDate() !== d) {
    throw new Error(`Not a real date: ${iso}`)
  }
  return date
}

function format(date: Date): string {
  return date.toISOString().slice(0, 10)
}

export function addDays(iso: string, days: number): string {
  return format(new Date(parse(iso).getTime() + days * DAY_MS))
}

/** The Monday of the week containing `iso`. */
export function weekStartOf(iso: string): string {
  const daysSinceMonday = (parse(iso).getUTCDay() + 6) % 7
  return addDays(iso, -daysSinceMonday)
}

export function addWeeks(iso: string, weeks: number): string {
  return addDays(weekStartOf(iso), weeks * 7)
}

/** "17 Aug – 23 Aug" for the week starting `weekStart`. */
export function formatWeekRange(weekStart: string): string {
  const label = (iso: string) => {
    const d = parse(iso)
    return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`
  }
  return `${label(weekStart)} – ${label(addDays(weekStart, 6))}`
}

/** Today's date in Africa/Johannesburg, whatever the browser's own zone is. */
export function todayInJohannesburg(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Africa/Johannesburg',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now)
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? ''
  return `${get('year')}-${get('month')}-${get('day')}`
}
