import type { ContractRow } from './types'

/** "80% in 20 s": what the customer is promised. */
export function promise(c: Pick<ContractRow, 'slTargetPct' | 'slThresholdS'>): string {
  return `${c.slTargetPct}% in ${c.slThresholdS} s`
}

/** The measured service level in words, or why there is none: never a made-up zero. */
export function measured(c: Pick<ContractRow, 'measuredSlPct' | 'offered'>): string {
  if (c.measuredSlPct === null) return 'No calls in the last 28 days'
  return `${c.measuredSlPct.toFixed(1)}% from ${c.offered.toLocaleString('en-ZA')} calls`
}

/** This week's coverage in words, from the roster against the published forecast. */
export function coverage(c: Pick<ContractRow, 'intervalsKnown' | 'underIntervals'>): string {
  if (c.intervalsKnown === 0) return 'No forecast for this week'
  if (c.underIntervals === 0) return 'Covered'
  return `${c.underIntervals} half-hours short`
}
