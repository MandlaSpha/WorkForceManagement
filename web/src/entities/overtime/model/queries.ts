import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import { fetchOvertime, fetchPay, fetchStandby, fetchSummary } from '../api/overtime'

/** Any change to a request or to pay invalidates `all`. */
export const overtimeKeys = {
  all: ['overtime'] as const,
  list: (status: string | null) => ['overtime', 'list', status] as const,
  pay: ['overtime', 'pay'] as const,
  standby: ['overtime', 'standby'] as const,
  summary: (month: string) => ['overtime', 'summary', month] as const,
}

export function useOvertime(status: MaybeRef<string | null> = null) {
  return useQuery({
    queryKey: computed(() => overtimeKeys.list(toValue(status))),
    queryFn: () => fetchOvertime(toValue(status)),
  })
}

export function usePay(enabled: MaybeRef<boolean> = true) {
  return useQuery({ queryKey: overtimeKeys.pay, queryFn: fetchPay, enabled })
}

export function useStandby() {
  return useQuery({ queryKey: overtimeKeys.standby, queryFn: fetchStandby })
}

export function useSummary(month: MaybeRef<string>, enabled: MaybeRef<boolean> = true) {
  return useQuery({
    queryKey: computed(() => overtimeKeys.summary(toValue(month))),
    queryFn: () => fetchSummary(toValue(month)),
    enabled,
  })
}
