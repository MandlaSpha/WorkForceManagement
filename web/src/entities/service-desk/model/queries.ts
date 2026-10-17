import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import { fetchDemand, fetchServiceKpis } from '../api/service-desk'

/** Bringing work in or changing a pool's productive time invalidates `all`. */
export const serviceDeskKeys = {
  all: ['service-desk'] as const,
  kpis: (month: string) => ['service-desk', 'kpis', month] as const,
  demand: (asOf: string, days: number) => ['service-desk', 'demand', asOf, days] as const,
}

export function useDemand(asOf: MaybeRef<string>, days: MaybeRef<number>) {
  return useQuery({
    queryKey: computed(() => serviceDeskKeys.demand(toValue(asOf), toValue(days))),
    queryFn: () => fetchDemand(toValue(asOf), toValue(days)),
  })
}

export function useServiceKpis(month: MaybeRef<string>) {
  return useQuery({
    queryKey: computed(() => serviceDeskKeys.kpis(toValue(month))),
    queryFn: () => fetchServiceKpis(toValue(month)),
  })
}
