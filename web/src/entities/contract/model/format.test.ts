import { describe, expect, it } from 'vitest'

import { coverage, measured, promise } from './format'

describe('contract wording', () => {
  it('states the promise as a percentage inside a number of seconds', () => {
    expect(promise({ slTargetPct: 80, slThresholdS: 20 })).toBe('80% in 20 s')
  })

  it('shows the measured service level with the calls it rests on', () => {
    expect(measured({ measuredSlPct: 75, offered: 1200 })).toMatch(/^75\.0% from 1.200 calls$/u)
  })

  it('says there is no figure rather than showing zero when there were no calls', () => {
    // Failure caught: a 0% that looks like a disaster when it is only an absence of data (DAT-10).
    expect(measured({ measuredSlPct: null, offered: 0 })).toBe('No calls in the last 28 days')
  })

  it('tells a covered week from a short one from one with no forecast', () => {
    expect(coverage({ intervalsKnown: 0, underIntervals: 0 })).toBe('No forecast for this week')
    expect(coverage({ intervalsKnown: 48, underIntervals: 0 })).toBe('Covered')
    expect(coverage({ intervalsKnown: 48, underIntervals: 17 })).toBe('17 half-hours short')
  })
})
