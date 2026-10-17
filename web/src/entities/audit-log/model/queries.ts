import { useQuery } from '@tanstack/vue-query'
import { toValue, type MaybeRefOrGetter } from 'vue'

import { fetchAuditChain, fetchAuditEvents, fetchAuditOptions } from '../api/audit'
import type { AuditFilters } from './types'

export const auditKeys = {
  events: (filters: AuditFilters, page: number) => ['audit', 'events', filters, page] as const,
  options: ['audit', 'options'] as const,
  chain: ['audit', 'chain'] as const,
}

/** Reading the log is itself recorded, so a search is fetched once and never refreshed in the
 * background (no refetch on focus or reconnect). */
const ONCE = { staleTime: Infinity, refetchOnWindowFocus: false, refetchOnReconnect: false }

export function useAuditEvents(
  filters: MaybeRefOrGetter<AuditFilters>,
  page: MaybeRefOrGetter<number>,
) {
  return useQuery({
    queryKey: () => auditKeys.events(toValue(filters), toValue(page)),
    queryFn: () => fetchAuditEvents(toValue(filters), toValue(page)),
    ...ONCE,
    placeholderData: (previous) => previous,
  })
}

export function useAuditOptions() {
  return useQuery({ queryKey: auditKeys.options, queryFn: fetchAuditOptions, ...ONCE })
}

export function useAuditChain() {
  return useQuery({ queryKey: auditKeys.chain, queryFn: fetchAuditChain, ...ONCE })
}
