import type {
  ForecastEvent,
  ForecastInterval,
  ForecastRange,
  ForecastVersion,
} from '@/entities/forecast'
import { dayOf, timeOf } from '@/shared/lib/datetime'

/** What the range endpoint answers, worked out the way the server does it, from the same
 * half-hours the day view uses. A day with none is "no forecast", never zero. */
export function rangeOf(
  version: ForecastVersion,
  intervals: ForecastInterval[],
  from: string,
  to: string,
  detail: boolean,
  events: ForecastEvent[] = [],
): ForecastRange {
  const days: ForecastRange['days'] = []
  for (
    const d = new Date(`${from}T00:00:00Z`);
    d <= new Date(`${to}T00:00:00Z`);
    d.setUTCDate(d.getUTCDate() + 1)
  ) {
    const day = d.toISOString().slice(0, 10)
    const rows = intervals.filter((i) => dayOf(i.start) === day)
    if (rows.length === 0) {
      const inside = day >= version.dateFrom && day <= version.dateTo
      days.push({
        day,
        hasForecast: false,
        reason: inside ? 'no_history' : 'outside_version',
        calls: null,
        ahtS: null,
        peakRequired: null,
        hoursRequired: null,
        complete: true,
        busiestSlot: null,
        requiredBySlot: null,
      })
      continue
    }
    const grid = Array.from({ length: 48 }, () => 0 as number | null)
    let calls = 0
    let busiest: { slot: number; volume: number } | null = null
    for (const row of rows) {
      const [hh, mm] = timeOf(row.start).split(':').map(Number) as [number, number]
      const slot = hh * 2 + (mm >= 30 ? 1 : 0)
      calls += row.volume
      grid[slot] = row.volume > 0 ? row.required : 0
      if (row.volume > 0 && (busiest === null || row.volume > busiest.volume)) {
        busiest = { slot, volume: row.volume }
      }
    }
    const known = grid.filter((n): n is number => n !== null)
    const complete = known.length === grid.length
    days.push({
      day,
      hasForecast: true,
      reason: null,
      calls,
      ahtS: 180,
      peakRequired: complete ? Math.max(...known) : null,
      hoursRequired: complete ? known.reduce((a, b) => a + b, 0) / 2 : null,
      complete,
      busiestSlot: busiest?.slot ?? null,
      requiredBySlot: detail ? grid : null,
    })
  }
  const forecast = days.filter((d) => d.hasForecast)
  const named = forecast.length >= 2 && new Set(forecast.map((d) => d.calls)).size > 1
  const ranked = [...forecast].sort((a, b) => (b.calls ?? 0) - (a.calls ?? 0))
  return {
    versionId: version.id,
    queue: version.queue,
    status: version.status,
    label: version.label,
    dateFrom: from,
    dateTo: to,
    versionDateFrom: version.dateFrom,
    versionDateTo: version.dateTo,
    days,
    busiestDay: named ? (ranked[0]?.day ?? null) : null,
    quietestDay: named ? (ranked[ranked.length - 1]?.day ?? null) : null,
    events: events
      .filter((e) => e.dateFrom <= to && e.dateTo >= from)
      .map((e) => ({
        name: e.name,
        dateFrom: e.dateFrom,
        dateTo: e.dateTo,
        upliftPct: e.upliftPct,
      })),
  }
}
