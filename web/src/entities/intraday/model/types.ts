import type { components } from '@/shared/api'

export type Intraday = components['schemas']['IntradayOut']
export type IntradayAlert = components['schemas']['IntradayAlertOut']
export type IntradaySuggestions = components['schemas']['IntradaySuggestionsOut']
export type IntradaySuggestedPerson = components['schemas']['IntradayPersonOut']
export type IntradayBreakMove = components['schemas']['IntradayBreakOut']

/** "09:30" for half-hour 19. */
export function slotLabel(slot: number): string {
  return `${String(Math.floor(slot / 2)).padStart(2, '0')}:${slot % 2 === 0 ? '00' : '30'}`
}
