import type { Score } from './types'

/** "93.5%", or a dash when a score could not be worked out. Never a made-up 0%. */
export function pctLabel(value: number | null, digits = 1): string {
  return value === null ? '\u2014' : `${value.toFixed(digits)}%`
}

/** The bias with its sign and what it means: "+12.3% (ran high)", "\u221248.2% (ran low)". */
export function biasLabel(bias: number | null): string {
  if (bias === null) return '\u2014'
  const rounded = Number(bias.toFixed(1))
  if (rounded === 0) return '0.0% (balanced)'
  const sign = rounded > 0 ? '+' : '\u2212'
  return `${sign}${Math.abs(rounded).toFixed(1)}% (ran ${rounded > 0 ? 'high' : 'low'})`
}

/** Whether the candidate did better, worse or the same on day totals, to one decimal. */
export function verdict(candidate: Score, current: Score): 'better' | 'worse' | 'same' | 'unknown' {
  if (candidate.dailyPct === null || current.dailyPct === null) return 'unknown'
  const a = Number(candidate.dailyPct.toFixed(1))
  const b = Number(current.dailyPct.toFixed(1))
  return a > b ? 'better' : a < b ? 'worse' : 'same'
}
