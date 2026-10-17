import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import { fetchCosts, fetchUtilisation } from '../api/utilisation'

export const utilisationKeys = { all: ['utilisation'] as const }

export function useUtilisation(month: MaybeRef<string>) {
  return useQuery({
    queryKey: computed(() => [...utilisationKeys.all, 'report', toValue(month)] as const),
    queryFn: () => fetchUtilisation(toValue(month)),
  })
}

/** `enabled` is false for roles that may not see pay, so the call is not even made. */
export function useCosts(month: MaybeRef<string>, enabled: MaybeRef<boolean>) {
  return useQuery({
    queryKey: computed(() => [...utilisationKeys.all, 'costs', toValue(month)] as const),
    queryFn: () => fetchCosts(toValue(month)),
    enabled: computed(() => toValue(enabled)),
  })
}
