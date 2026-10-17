import type { Capacity, CapacityDay, Limits } from '@/entities/workforce/capacity'

import { DAYS, WEEK } from './scheduling-fixtures'

export const LIMITS: Limits = { permanentLimit: 100, seasonalLimit: 250, confirmed: true }

const NOTHING = {
  peak: null,
  permanent: null,
  seasonal: null,
  overflow: null,
  seasonalToHire: null,
}

export function dayOf(day: string, overrides: Partial<CapacityDay> = {}): CapacityDay {
  return {
    day,
    queuesCovered: 0,
    queuesTotal: 2,
    complete: false,
    permanentOnBooks: 0,
    seasonalOnBooks: 0,
    ...NOTHING,
    ...overrides,
  }
}

/** The week of the API tests, worked by hand: Monday 160 needed (100 permanent + 60 seasonal),
 * Tuesday 200 but only one queue forecast (a minimum), Wednesday 410 (60 beyond everyone), and
 * nothing forecast for the rest. */
export function capacityOf(overrides: Partial<Capacity> = {}): Capacity {
  const days = [
    dayOf(DAYS[0]!, {
      queuesCovered: 2,
      complete: true,
      peak: 160,
      permanent: 100,
      seasonal: 60,
      overflow: 0,
      seasonalToHire: 60,
      permanentOnBooks: 2,
    }),
    dayOf(DAYS[1]!, {
      queuesCovered: 1,
      peak: 200,
      permanent: 100,
      seasonal: 100,
      overflow: 0,
      seasonalToHire: 100,
    }),
    dayOf(DAYS[2]!, {
      queuesCovered: 2,
      complete: true,
      peak: 410,
      permanent: 100,
      seasonal: 250,
      overflow: 60,
      seasonalToHire: 247,
      seasonalOnBooks: 3,
    }),
    ...DAYS.slice(3).map((d) => dayOf(d)),
  ]
  return {
    limits: LIMITS,
    weeks: [
      {
        weekStart: WEEK,
        peak: 410,
        peakDay: DAYS[2]!,
        seasonalPeak: 250,
        overflowDays: 1,
        daysForecast: 3,
        daysIncomplete: 1,
        days,
      },
    ],
    ...overrides,
  }
}

/** Nothing forecast anywhere. */
export function emptyCapacity(limits: Limits = LIMITS): Capacity {
  return {
    limits,
    weeks: [
      {
        weekStart: WEEK,
        peak: null,
        peakDay: null,
        seasonalPeak: null,
        overflowDays: 0,
        daysForecast: 0,
        daysIncomplete: 0,
        days: DAYS.map((d) => dayOf(d)),
      },
    ],
  }
}
