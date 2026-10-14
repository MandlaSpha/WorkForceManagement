import { describe, expect, it } from 'vitest'

import { biasLabel, pctLabel, verdict } from './tuning'

const score = (dailyPct: number | null) => ({ dailyPct, intervalPct: null, biasPct: null, days: 2 })

describe('pctLabel', () => {
  it('shows a dash for a score that could not be worked out, never 0%', () => {
    expect(pctLabel(null)).toBe('\u2014')
    expect(pctLabel(0)).toBe('0.0%')
    expect(pctLabel(51.757)).toBe('51.8%')
  })
})

describe('biasLabel', () => {
  it('says which way the forecasts ran, with a real minus sign', () => {
    expect(biasLabel(12.34)).toBe('+12.3% (ran high)')
    expect(biasLabel(-48.24)).toBe('\u221248.2% (ran low)')
  })

  it('calls a bias that rounds to nothing balanced, and has no bias without data', () => {
    expect(biasLabel(0.04)).toBe('0.0% (balanced)')
    expect(biasLabel(null)).toBe('\u2014')
  })
})

describe('verdict', () => {
  it('compares on day totals to one decimal', () => {
    expect(verdict(score(60), score(51.76))).toBe('better')
    expect(verdict(score(40), score(51.76))).toBe('worse')
    expect(verdict(score(51.76), score(51.8))).toBe('same') // both are 51.8 to one decimal
  })

  it('does not call it either way when a side is unknown', () => {
    expect(verdict(score(null), score(50))).toBe('unknown')
  })
})
