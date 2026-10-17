import type { components } from '@/shared/api'

export type Wellbeing = components['schemas']['WellbeingOut']
export type WellbeingPerson = components['schemas']['WellbeingPersonOut']

/** What to say for each prompt. The number is a fact (days), never a score of the person. */
export function flagText(code: string, value: number): string {
  switch (code) {
    case 'long_run':
      return `${value} days worked in a row`
    case 'no_rest':
      return `${value} day${value === 1 ? '' : 's'} off in the last fortnight`
    case 'repeated_overtime':
      return `Overtime on ${value} different days in the last four weeks`
    case 'rising_absence':
      return `${value} days of unplanned absence in the last four weeks, more than the four before`
    default:
      return 'Worth a conversation'
  }
}
