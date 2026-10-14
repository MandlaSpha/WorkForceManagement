import { describe, expect, it } from 'vitest'

import type { ForecastInterval, ForecastVersion } from './types'
import { dayPoints, forecastDays, historyAgeDays, summarise } from './chart'

const interval = (start: string, volume: number, required: number | null): ForecastInterval => ({
  start,
  volume,
  ahtS: 180,
  requiredRaw: required,
  required,
  daysUsed: 3,
  volumeLower: null,
  volumeUpper: null,
})

const version = (overrides: Partial<ForecastVersion> = {}): ForecastVersion => ({
  id: 'v1',
  queueId: 1,
  queue: 'QueueA',
  label: '',
  status: 'draft',
  method: 'baseline-v1',
  dateFrom: '2026-05-25',
  dateTo: '2026-05-31',
  createdAt: '2026-05-20T08:00:00Z',
  createdBy: 'Pat Planner',
  publishedAt: null,
  intervalCount: 48,
  assumptionsConfirmed: false,
  fallback: null,
  daysWithoutHistory: [],
  historyThrough: '2026-05-18',
  params: {},
  ...overrides,
})

describe('dayPoints', () => {
  it('puts a half-hour on the South African day it belongs to, in time order', () => {
    const intervals = [
      interval('2026-05-25T08:30:00Z', 12, 5), // 10:30 on 25 May
      interval('2026-05-25T08:00:00Z', 20, 6), // 10:00 on 25 May
      interval('2026-05-25T22:00:00Z', 1, 1), // midnight: already 26 May in Johannesburg
    ]
    const points = dayPoints(intervals, '2026-05-25')
    expect(points.map((p) => p.label)).toEqual(['10:00', '10:30'])
    expect(dayPoints(intervals, '2026-05-26').map((p) => p.label)).toEqual(['00:00'])
  })
})

describe('forecastDays', () => {
  it('lists the days of the range that have a forecast, leaving out the ones that could not', () => {
    const days = forecastDays(
      version({ daysWithoutHistory: ['2026-05-26', '2026-05-27', '2026-05-28'] }),
    )
    expect(days).toEqual(['2026-05-25', '2026-05-29', '2026-05-30', '2026-05-31'])
  })

  it('crosses a month end', () => {
    const days = forecastDays(version({ dateFrom: '2026-05-30', dateTo: '2026-06-02' }))
    expect(days).toEqual(['2026-05-30', '2026-05-31', '2026-06-01', '2026-06-02'])
  })
})

describe('summarise', () => {
  it('finds the busiest half-hour and the most agents needed', () => {
    const points = dayPoints(
      [
        interval('2026-05-25T07:30:00Z', 4, 3),
        interval('2026-05-25T08:00:00Z', 20, 6),
        interval('2026-05-25T08:30:00Z', 12, 5),
      ],
      '2026-05-25',
    )
    const summary = summarise(points)
    expect(summary.totalVolume).toBeCloseTo(36)
    expect(summary.peak?.label).toBe('10:00')
    expect(summary.maxRequired).toBe(6)
  })

  it('has no peak on a day with no calls, instead of calling a quiet half-hour the busiest', () => {
    const points = dayPoints([interval('2026-05-25T08:00:00Z', 0, 0)], '2026-05-25')
    expect(summarise(points).peak).toBeNull()
  })

  it('does not treat a missing requirement as zero agents', () => {
    const points = dayPoints([interval('2026-05-25T08:00:00Z', 5, null)], '2026-05-25')
    expect(summarise(points).maxRequired).toBeNull()
  })

  it('claims no maximum when a busy half-hour has no requirement, even if quiet ones do', () => {
    // The unknown half-hour could need more than the 3 we do know, so 3 must not be reported.
    const points = dayPoints(
      [
        interval('2026-05-25T07:30:00Z', 4, 3),
        interval('2026-05-25T08:00:00Z', 20, null),
        interval('2026-05-25T08:30:00Z', 0, 0),
      ],
      '2026-05-25',
    )
    expect(summarise(points).maxRequired).toBeNull()
  })

  it('still reports the maximum when only quiet half-hours lack a requirement', () => {
    const points = dayPoints(
      [interval('2026-05-25T08:00:00Z', 20, 6), interval('2026-05-25T08:30:00Z', 0, null)],
      '2026-05-25',
    )
    expect(summarise(points).maxRequired).toBe(6)
  })
})

describe('historyAgeDays', () => {
  it('counts the days between the newest data and the first forecast day', () => {
    expect(historyAgeDays(version())).toBe(7)
    expect(historyAgeDays(version({ dateFrom: '2026-07-01', historyThrough: '2026-05-31' }))).toBe(
      31,
    )
  })

  it('has no answer when the API did not say', () => {
    expect(historyAgeDays(version({ historyThrough: null }))).toBeNull()
  })
})

describe('the range of a day', () => {
  const point = (lower: number | null, upper: number | null) => ({
    label: '10:00',
    volume: 10,
    required: 1,
    requiredRaw: 1,
    daysUsed: 3,
    lower,
    upper,
  })

  it('adds up the half-hour ranges', () => {
    const day = summarise([point(8, 13), point(4, 6)])
    expect([day.totalLower, day.totalUpper]).toEqual([12, 19])
  })

  it('claims no range when any half-hour lacks one, rather than a partial figure', () => {
    const day = summarise([point(8, 13), point(null, null)])
    expect([day.totalLower, day.totalUpper]).toEqual([null, null])
  })

  it('claims no range for a day with no half-hours at all', () => {
    expect(summarise([]).totalLower).toBeNull()
  })
})
