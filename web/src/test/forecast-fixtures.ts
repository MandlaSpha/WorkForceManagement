import type { QueueInfo } from '@/entities/call-data'
import type {
  Backtest,
  ForecastAccuracy,
  ForecastInterval,
  ForecastVersion,
  ScenarioResult,
  Tuning,
} from '@/entities/forecast'

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
    outboundOnly: false,
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
    fallback: null,
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
      volumeLower: null,
      volumeUpper: null,
      ahtS: hit ? 180 : null,
      requiredRaw: hit?.raw ?? 0,
      required: hit?.required ?? 0,
      daysUsed: 3,
    }
  })
}

/** The scenario of the API tests worked by hand: 10 calls at 10:00 need 5 to roster; twice the
 * calls need 6. */
export function scenarioResult(overrides: Partial<ScenarioResult> = {}): ScenarioResult {
  const assumptions = {
    slTargetPct: 80,
    slThresholdS: 20,
    occupancyCeilingPct: 85,
    shrinkagePct: 30,
  }
  return {
    versionId: 'v-live',
    queue: 'QueueA',
    base: assumptions,
    scenario: assumptions,
    days: [
      {
        day: '2026-05-25',
        callsBase: 10,
        callsScenario: 20,
        peakBase: 5,
        peakScenario: 6,
        hoursBase: 2.5,
        hoursScenario: 3,
        complete: true,
      },
    ],
    ...overrides,
  }
}

export function accuracyFor(overrides: Partial<ForecastAccuracy> = {}): ForecastAccuracy {
  return {
    queueId: 1,
    queue: 'QueueA',
    overallAccuracyPct: 81.448,
    overallDailyAccuracyPct: 90.2,
    biasPct: null,
    weeks: 4,
    decay: 0.7,
    days: [
      { date: '2026-05-11', accuracyPct: 83.333, dailyAccuracyPct: 90, daysUsed: 1 },
      { date: '2026-05-18', accuracyPct: 79.832, dailyAccuracyPct: 90.4, daysUsed: 2 },
    ],
    ...overrides,
  }
}

export function tuningOf(overrides: Partial<Tuning> = {}): Tuning {
  return {
    queueId: 1,
    queue: 'QueueA',
    weeks: 4,
    decay: 0.7,
    volumeMultiplier: 1,
    ahtMultiplier: 1,
    saved: false,
    ...overrides,
  }
}

/** The back-test of the API tests, worked by hand on a rising queue (10, 20 and 30 calls): the
 * saved tuning (4 weeks) gets day totals 51.76% right and runs 48.24% low; looking back one week
 * gets 60% right and runs 40% low. The multiplier that removes the bias is 1.67. */
export function backtestOf(overrides: Partial<Backtest> = {}): Backtest {
  return {
    queueId: 1,
    candidate: { dailyPct: 60, intervalPct: 55.5, biasPct: -40, days: 2 },
    current: { dailyPct: 51.76, intervalPct: 48.1, biasPct: -48.24, days: 2 },
    suggestedVolumeMultiplier: 1.67,
    ...overrides,
  }
}
