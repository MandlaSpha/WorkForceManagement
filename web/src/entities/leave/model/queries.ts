import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import {
  fetchAwayLimit,
  fetchBalances,
  fetchBlackouts,
  fetchImpact,
  fetchLeaveTypes,
  fetchRequests,
} from '../api/leave'

/** Applying for, deciding on or cancelling leave invalidates `all`. */
export const leaveKeys = {
  all: ['leave'] as const,
  types: ['leave', 'types'] as const,
  balances: (year: number) => ['leave', 'balances', year] as const,
  requests: (status: string | null) => ['leave', 'requests', status] as const,
  impact: (requestId: number) => ['leave', 'impact', requestId] as const,
  blackouts: ['leave', 'blackouts'] as const,
  limit: ['leave', 'limit'] as const,
}

export function useLeaveTypes() {
  return useQuery({ queryKey: leaveKeys.types, queryFn: fetchLeaveTypes })
}

export function useBalances(year: MaybeRef<number>) {
  return useQuery({
    queryKey: computed(() => leaveKeys.balances(toValue(year))),
    queryFn: () => fetchBalances(toValue(year)),
    retry: false, // "not on the employee list" is an answer, not a glitch
  })
}

export function useRequests(status: MaybeRef<string | null>) {
  return useQuery({
    queryKey: computed(() => leaveKeys.requests(toValue(status))),
    queryFn: () => fetchRequests(toValue(status)),
  })
}

export function useImpact(requestId: MaybeRef<number>, enabled: MaybeRef<boolean>) {
  return useQuery({
    queryKey: computed(() => leaveKeys.impact(toValue(requestId))),
    queryFn: () => fetchImpact(toValue(requestId)),
    enabled: computed(() => toValue(enabled)),
  })
}

export function useBlackouts() {
  return useQuery({ queryKey: leaveKeys.blackouts, queryFn: fetchBlackouts })
}

export function useAwayLimit() {
  return useQuery({ queryKey: leaveKeys.limit, queryFn: fetchAwayLimit })
}
