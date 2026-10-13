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
