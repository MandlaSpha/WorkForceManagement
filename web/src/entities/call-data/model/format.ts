/**
 * How call-data figures are written. A missing figure is "—", never "0" or "0%": no calls means
 * no figure, and a zero would read as "perfect" (requirement DAT-10).
 */

export const NO_FIGURE = '—'

export function formatCount(value: number): string {
  return value.toLocaleString('en-ZA')
}

export function formatPercent(value: number | null, digits = 1): string {
  return value === null ? NO_FIGURE : `${value.toFixed(digits)}%`
}

/** Seconds as m:ss ("3:35"), or h:mm:ss from an hour up. Rounds to the nearest second. */
export function formatDuration(seconds: number | null): string {
  if (seconds === null) return NO_FIGURE
  const total = Math.round(seconds)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const rest = String(total % 60).padStart(2, '0')
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, '0')}:${rest}` : `${minutes}:${rest}`
}

/** Seconds to one decimal place ("18.5 s"), for waits that are short enough to need it. */
export function formatSeconds(seconds: number | null): string {
  return seconds === null ? NO_FIGURE : `${seconds.toFixed(1)} s`
}
