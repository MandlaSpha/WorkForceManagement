import type { components } from '@/shared/api'

export type AuditEvent = components['schemas']['AuditEventOut']
export type AuditChange = components['schemas']['AuditChangeOut']
export type AuditEventPage = components['schemas']['AuditEventPageOut']
export type AuditOptions = components['schemas']['AuditOptionsOut']
export type AuditChain = components['schemas']['AuditChainOut']

/** What the admin typed into the filter bar. Days are South African calendar days (`YYYY-MM-DD`). */
export interface AuditFilters {
  actor: string
  action: string
  entityType: string
  outcome: string
  fromDay: string
  toDay: string
}

export const NO_FILTERS: AuditFilters = {
  actor: '',
  action: '',
  entityType: '',
  outcome: '',
  fromDay: '',
  toDay: '',
}
