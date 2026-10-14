import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import { fetchMyShifts, fetchOptions, fetchSwaps } from '../api/swap'

/** Offering, answering or withdrawing a swap invalidates `all`. */
export const swapKeys = {
  all: ['swaps'] as const,
  mine: ['swaps', 'my-shifts'] as const,
  options: (giveId: number) => ['swaps', 'options', giveId] as const,
  list: (status: string | null) => ['swaps', 'list', status] as const,
}

export function useMyShifts() {
  return useQuery({ queryKey: swapKeys.mine, queryFn: fetchMyShifts, retry: false })
}

export function useOptions(giveId: MaybeRef<number | null>) {
  return useQuery({
    queryKey: computed(() => swapKeys.options(toValue(giveId) ?? 0)),
    queryFn: () => fetchOptions(toValue(giveId) as number),
    enabled: computed(() => toValue(giveId) !== null),
  })
}

export function useSwaps(status: MaybeRef<string | null>) {
  return useQuery({
    queryKey: computed(() => swapKeys.list(toValue(status))),
    queryFn: () => fetchSwaps(toValue(status)),
  })
}
