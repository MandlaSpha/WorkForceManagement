import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import { fetchBoard, fetchMyShifts, fetchOffers, fetchSwaps } from '../api/swap'

/** Offering, answering or withdrawing a swap invalidates `all`. */
export const swapKeys = {
  all: ['swaps'] as const,
  mine: ['swaps', 'my-shifts'] as const,
  board: ['swaps', 'board'] as const,
  offers: (swapId: number) => ['swaps', 'offers', swapId] as const,
  list: (status: string | null) => ['swaps', 'list', status] as const,
}

export function useMyShifts() {
  return useQuery({ queryKey: swapKeys.mine, queryFn: fetchMyShifts, retry: false })
}

export function useBoard() {
  return useQuery({ queryKey: swapKeys.board, queryFn: fetchBoard, retry: false })
}

export function useOffers(swapId: MaybeRef<number>, enabled: MaybeRef<boolean>) {
  return useQuery({
    queryKey: computed(() => swapKeys.offers(toValue(swapId))),
    queryFn: () => fetchOffers(toValue(swapId)),
    enabled: computed(() => toValue(enabled)),
  })
}

export function useSwaps(status: MaybeRef<string | null>) {
  return useQuery({
    queryKey: computed(() => swapKeys.list(toValue(status))),
    queryFn: () => fetchSwaps(toValue(status)),
  })
}
