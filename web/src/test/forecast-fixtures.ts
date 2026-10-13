import type { QueueInfo } from '@/entities/call-data'
import type { ForecastAccuracy, ForecastInterval, ForecastVersion } from '@/entities/forecast'

export function queueInfo(overrides: Partial<QueueInfo> = {}): QueueInfo {
  return {
    id: 1,
    name: 'QueueA',
    confirmed: true,
    slTargetPct: 80,
    slThresholdS: 20,
    occupancyCeilingPct: 85,
    shrinkagePct: 30,
    settingsConfirmed: false,
    ...overrides,
  }
}

export function forecastVersion(overrides: Partial<ForecastVersion> = {}): ForecastVersion {
  return {
    id: 'v-live',
    queueId: 1,
    queue: 'QueueA',
    label: 'Week 22',
    status: 'published',
    method: 'baseline-v1',
    dateFrom: '2026-05-25',
    dateTo: '2026-05-25',
    createdAt: '2026-05-20T08:00:00Z',
    createdBy: 'Pat Planner',
    publishedAt: '2026-05-20T09:00:00Z',
    intervalCount: 48,
    assumptionsConfirmed: false,
    daysWithoutHistory: [],
    historyThrough: '2026-05-18',
    params: { slTargetPct: 80, slThresholdS: 20, occupancyCeilingPct: 85, shrinkagePct: 30 },
    ...overrides,
  }
}

/** All 48 half-hours of a South African day. Quiet except 10:00 (19.9 calls, 6 agents to roster)
 * and 10:30 (12 calls, 5 agents), so the busiest half-hour is 10:00. */
export function dayIntervals(day = '2026-05-25'): ForecastInterval[] {
  const [year, month, date] = day.split('-').map(Number) as [number, number, number]
  return Array.from({ length: 48 }, (_, slot) => {
    // Johannesburg is UTC+2: midnight there is 22:00 UTC the day before.
    const start = new Date(Date.UTC(year, month - 1, date, -2, slot * 30)).toISOString()
    const busy = slot === 20 ? { volume: 19.9, required: 6, raw: 4 } : undefined
    const next = slot === 21 ? { volume: 12, required: 5, raw: 3 } : undefined
    const hit = busy ?? next
    return {
      start,
      volume: hit?.volume ?? 0,
      ahtS: hit ? 180 : null,
      requiredRaw: hit?.raw ?? 0,
      required: hit?.required ?? 0,
      daysUsed: 3,
    }
  })
}

export function accuracyFor(overrides: Partial<ForecastAccuracy> = {}): ForecastAccuracy {
  return {
    queueId: 1,
    queue: 'QueueA',
    overallAccuracyPct: 81.448,
    overallDailyAccuracyPct: 90.2,
    weeks: 4,
    decay: 0.7,
    days: [
      { date: '2026-05-11', accuracyPct: 83.333, dailyAccuracyPct: 90, daysUsed: 1 },
      { date: '2026-05-18', accuracyPct: 79.832, dailyAccuracyPct: 90.4, daysUsed: 2 },
    ],
    ...overrides,
  }
}
