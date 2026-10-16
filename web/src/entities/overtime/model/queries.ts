import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import { fetchOvertime, fetchPay } from '../api/overtime'

/** Any change to a request or to pay invalidates `all`. */
export const overtimeKeys = {
  all: ['overtime'] as const,
  list: (status: string | null) => ['overtime', 'list', status] as const,
  pay: ['overtime', 'pay'] as const,
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
