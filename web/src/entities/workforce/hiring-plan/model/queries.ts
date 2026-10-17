import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import { fetchPlan, fetchPlans } from '../api/hiring-plan'

export const hiringKeys = {
  all: ['hiring-plans'] as const,
  list: ['hiring-plans', 'list'] as const,
  one: (id: number) => ['hiring-plans', 'one', id] as const,
}

export function useHiringPlans() {
  return useQuery({ queryKey: hiringKeys.list, queryFn: fetchPlans })
}

export function useHiringPlan(planId: MaybeRef<number | null>) {
  return useQuery({
    queryKey: computed(() => hiringKeys.one(toValue(planId) as number)),
    queryFn: () => fetchPlan(toValue(planId) as number),
    enabled: computed(() => toValue(planId) !== null),
  })
}
