import { describe, expect, it } from 'vitest'

import { deltaLabel, totalsOf } from './scenario'
import type { ScenarioDay } from './types'

const day = (over: Partial<ScenarioDay> = {}): ScenarioDay => ({
  day: '2026-05-25',
  callsBase: 10,
  callsScenario: 20,
  peakBase: 5,
  peakScenario: 6,
  hoursBase: 2.5,
  hoursScenario: 3,
  complete: true,
  ...over,
})

describe('deltaLabel', () => {
  it('signs a rise and a fall, using a real minus sign', () => {
    expect(deltaLabel(5, 6)).toBe('+1')
    expect(deltaLabel(6, 4)).toBe('\u22122')
  })

  it('says 0 when nothing changed', () => {
    expect(deltaLabel(5, 5)).toBe('0')
  })

  it('is a dash when either side is unknown, never a made-up zero', () => {
    expect(deltaLabel(null, 5)).toBe('\u2014')
    expect(deltaLabel(5, null)).toBe('\u2014')
  })

  it('keeps the decimals asked for and drops rounding noise', () => {
    expect(deltaLabel(2.5, 3, 1)).toBe('+0.5')
    expect(deltaLabel(0.1 + 0.2, 0.3, 1)).toBe('0')
  })
})

describe('totalsOf', () => {
  it('adds calls and hours, and takes the busiest day for the peak', () => {
    const t = totalsOf([day(), day({ day: '2026-05-26', peakBase: 9, peakScenario: 12 })])
    expect([t.callsBase, t.callsScenario, t.hoursBase, t.hoursScenario]).toEqual([20, 40, 5, 6])
    expect([t.peakBase, t.peakScenario]).toEqual([9, 12])
  })

  it('ignores a day with an unknown peak rather than counting it as zero', () => {
    const t = totalsOf([
      day({ peakBase: null, peakScenario: null }),
      day({ peakBase: 3, peakScenario: 4 }),
    ])
    expect([t.peakBase, t.peakScenario]).toEqual([3, 4])
  })

  it('has no peak when no day has one, and is complete only if every day is', () => {
    expect(totalsOf([day({ peakBase: null, peakScenario: null })]).peakScenario).toBeNull()
    expect(totalsOf([day(), day({ complete: false })]).complete).toBe(false)
    expect(totalsOf([]).peakBase).toBeNull()
  })
})
