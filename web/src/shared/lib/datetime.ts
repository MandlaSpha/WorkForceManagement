/** Timestamps arrive as UTC and are shown in South African time (store UTC, display SAST). */
const ZONE = 'Africa/Johannesburg'

const DATE = new Intl.DateTimeFormat('en-ZA', {
  timeZone: ZONE,
  day: 'numeric',
  month: 'short',
  year: 'numeric',
})
const DATE_TIME = new Intl.DateTimeFormat('en-ZA', {
  timeZone: ZONE,
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

export function formatDate(iso: string): string {
  return DATE.format(new Date(iso))
}

export function formatDateTime(iso: string): string {
  return DATE_TIME.format(new Date(iso))
}

const DAY = new Intl.DateTimeFormat('en-CA', {
  timeZone: ZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})
const TIME = new Intl.DateTimeFormat('en-ZA', {
  timeZone: ZONE,
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

/** The South African calendar day of a moment, as `YYYY-MM-DD`. */
export function dayOf(iso: string): string {
  return DAY.format(new Date(iso))
}

const HOUR = new Intl.DateTimeFormat('en-GB', { timeZone: ZONE, hour: '2-digit', hour12: false })
const LONG_DAY = new Intl.DateTimeFormat('en-ZA', {
  timeZone: ZONE,
  weekday: 'long',
  day: 'numeric',
  month: 'long',
})

/** morning / afternoon / evening by South African local time. */
export function partOfDay(now: Date): 'morning' | 'afternoon' | 'evening' {
  const hour = Number(HOUR.format(now)) % 24
  return hour < 12 ? 'morning' : hour < 18 ? 'afternoon' : 'evening'
}

/** "Good morning, Thandi". The name is for the screen only: never send it to telemetry or logs. */
export function greeting(now: Date, displayName: string | null | undefined): string {
  const first = (displayName ?? '').trim().split(/\s+/)[0] ?? ''
  return first ? `Good ${partOfDay(now)}, ${first}` : `Good ${partOfDay(now)}`
}

/** "Thursday 29 October" in South African time. */
export function longDay(now: Date): string {
  return LONG_DAY.format(now)
}

/** The South African clock time of a moment, as `HH:mm`. */
export function timeOf(iso: string): string {
  return TIME.format(new Date(iso))
}

const DAY_LABEL = new Intl.DateTimeFormat('en-ZA', {
  timeZone: 'UTC',
  weekday: 'short',
  day: 'numeric',
  month: 'short',
})

/** A plain calendar day (`YYYY-MM-DD`) for people: "Mon 25 May". No time zone is involved, so it
 * can never slip to the neighbouring day. */
export function formatDayLabel(day: string): string {
  return DAY_LABEL.format(new Date(`${day}T12:00:00Z`)).replace(',', '')
}

/** "just now", "5 min ago", "3 h ago", "2 d ago"; older than a week falls back to the date.
 * `now` is a parameter so the result is the same in a test and nothing here reads the clock. */
export function relativeTime(iso: string, now: Date): string {
  const seconds = Math.round((now.getTime() - new Date(iso).getTime()) / 1000)
  if (!Number.isFinite(seconds) || seconds < 45) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.round(hours / 24)
  if (days <= 7) return `${days} d ago`
  return new Intl.DateTimeFormat('en-ZA', {
    timeZone: 'Africa/Johannesburg',
    day: 'numeric',
    month: 'short',
  }).format(new Date(iso))
}
