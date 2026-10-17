import { api, unwrap } from '@/shared/api'

import { toQuery } from '../model/filters'
import type { AuditChain, AuditEventPage, AuditFilters, AuditOptions } from '../model/types'

export const PAGE_SIZE = 50

export async function fetchAuditEvents(
  filters: AuditFilters,
  page: number,
): Promise<AuditEventPage> {
  return unwrap(
    await api.GET('/api/v1/audit/events', {
      params: { query: { ...toQuery(filters), page, pageSize: PAGE_SIZE } },
    }),
  )
}

export async function fetchAuditOptions(): Promise<AuditOptions> {
  return unwrap(await api.GET('/api/v1/audit/options'))
}

export async function fetchAuditChain(): Promise<AuditChain> {
  return unwrap(await api.GET('/api/v1/audit/chain'))
}

/** The address of the CSV for these filters. The server records every download. */
export function auditCsvUrl(filters: AuditFilters): string {
  const query = new URLSearchParams(toQuery(filters)).toString()
  return `/api/v1/audit/events.csv${query ? `?${query}` : ''}`
}
