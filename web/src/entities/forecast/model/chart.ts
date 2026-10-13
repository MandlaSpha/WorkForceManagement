import { dayOf, timeOf } from '@/shared/lib/datetime'

import type { ForecastInterval, ForecastVersion } from './types'

/** One half-hour on the chart: expected calls, and the agents to roster for them. */
export interface Point {
  label: string // "10:00"
  volume: number
  required: number | null
  requiredRaw: number | null
  daysUsed: number
}

/** The half-hours of one South African day, in time order. */
export function dayPoints(intervals: ReadonlyArray<ForecastInterval>, day: string): Point[] {
  return intervals
    .filter((i) => dayOf(i.start) === day)
    .sort((a, b) => a.start.localeCompare(b.start))
    .map((i) => ({
      label: timeOf(i.start),
      volume: i.volume,
      required: i.required,
      requiredRaw: i.requiredRaw,
      daysUsed: i.daysUsed,
    }))
}

/** The days of the version that have a forecast: its range minus the days with no history. */
export function forecastDays(version: ForecastVersion): string[] {
  const days: string[] = []
  const end = new Date(`${version.dateTo}T00:00:00Z`)
  for (
    const day = new Date(`${version.dateFrom}T00:00:00Z`);
    day <= end;
    day.setUTCDate(day.getUTCDate() + 1)
  ) {
    days.push(day.toISOString().slice(0, 10))
  }
  return days.filter((d) => !version.daysWithoutHistory.includes(d))
}

export interface DaySummary {
  totalVolume: number
  peak: Point | null // the busiest half-hour
  maxRequired: number | null
}

export function summarise(points: ReadonlyArray<Point>): DaySummary {
  let peak: Point | null = null
  let maxRequired: number | null = null
  let someUnknown = false
  for (const point of points) {
    if (point.volume > 0 && (peak === null || point.volume > peak.volume)) peak = point
    if (point.volume > 0 && point.required === null) someUnknown = true
    if (point.required !== null && (maxRequired === null || point.required > maxRequired)) {
      maxRequired = point.required
    }
  }
  // If any half-hour with calls has no requirement, the true maximum could be higher than the
  // ones we know, so no maximum is claimed (DAT-10: never present a partial figure as complete).
  return {
    totalVolume: points.reduce((sum, p) => sum + p.volume, 0),
    peak,
    maxRequired: someUnknown ? null : maxRequired,
  }
}

/** How many days before the first forecast day the newest call data is. A forecast built on old
 * data is a rough guide, and the screen says so. */
export function historyAgeDays(version: ForecastVersion): number | null {
  if (!version.historyThrough) return null
  const newest = new Date(`${version.historyThrough}T00:00:00Z`).getTime()
  const first = new Date(`${version.dateFrom}T00:00:00Z`).getTime()
  return Math.round((first - newest) / 86_400_000)
}
