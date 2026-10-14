import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import { fetchDemand } from '../api/service-desk'

/** Bringing work in or changing a pool's productive time invalidates `all`. */
export const serviceDeskKeys = {
  all: ['service-desk'] as const,
  demand: (asOf: string, days: number) => ['service-desk', 'demand', asOf, days] as const,
}

export function useDemand(asOf: MaybeRef<string>, days: MaybeRef<number>) {
  return useQuery({
    queryKey: computed(() => serviceDeskKeys.demand(toValue(asOf), toValue(days))),
    queryFn: () => fetchDemand(toValue(asOf), toValue(days)),
  })
}
