export const WEEKDAYS = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
] as const

export const KIND_LABEL: Record<string, string> = {
  unavailable: 'Cannot work',
  preferred: 'Would rather work',
}

export const KIND_TONE: Record<string, string> = {
  unavailable: 'bg-danger-soft text-danger',
  preferred: 'bg-brand-soft text-brand-ink',
}

/** "09:00:00" -> "09:00". */
export function clock(time: string): string {
  return time.slice(0, 5)
}

/** "12:00-13:00", with an end of midnight written as "24:00" so it reads as the end of the day. */
export function windowLabel(start: string, end: string): string {
  return `${clock(start)}-${clock(end) === '00:00' ? '24:00' : clock(end)}`
}
