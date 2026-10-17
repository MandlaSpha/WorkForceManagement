import type { components } from '@/shared/api'

export type QualityImportReport = components['schemas']['QualityImportOut']
export type QualityTeam = components['schemas']['QualityTeamOut']
export type QualityPersonSummary = components['schemas']['QualityPersonSummaryOut']
export type QualityPerson = components['schemas']['QualityPersonOut']
export type QualityEvaluation = components['schemas']['QualityEvaluationOut']

export const KIND_LABEL: Record<string, string> = { call: 'Call', ticket: 'Ticket' }

/** "86.5%", or a dash when there is nothing to average (never 0). */
export function scoreText(value: number | null): string {
  return value === null ? '—' : `${value.toFixed(1)}%`
}
