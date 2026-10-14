import type { ScenarioDay } from './types'

/** The change from base to scenario, signed with a real minus sign: "+1", "\u22122" or "0".
 * Unknown on either side is a dash, never a made-up zero. */
export function deltaLabel(base: number | null, scenario: number | null, digits = 0): string {
  if (base === null || scenario === null) return '\u2014'
  const change = Number((scenario - base).toFixed(digits))
  if (change === 0) return '0'
  return change > 0 ? `+${change}` : `\u2212${Math.abs(change)}`
}

export interface ScenarioTotals {
  callsBase: number
  callsScenario: number
  peakBase: number | null
  peakScenario: number | null
  hoursBase: number
  hoursScenario: number
  complete: boolean
}

/** The whole range at a glance: calls and agent-hours add up, the peak is the busiest day's. */
export function totalsOf(days: ReadonlyArray<ScenarioDay>): ScenarioTotals {
  const peak = (values: Array<number | null>): number | null => {
    const known = values.filter((v): v is number => v !== null)
    return known.length > 0 ? Math.max(...known) : null
  }
  return {
    callsBase: days.reduce((sum, d) => sum + d.callsBase, 0),
    callsScenario: days.reduce((sum, d) => sum + d.callsScenario, 0),
    peakBase: peak(days.map((d) => d.peakBase)),
    peakScenario: peak(days.map((d) => d.peakScenario)),
    hoursBase: days.reduce((sum, d) => sum + d.hoursBase, 0),
    hoursScenario: days.reduce((sum, d) => sum + d.hoursScenario, 0),
    complete: days.every((d) => d.complete),
  }
}
