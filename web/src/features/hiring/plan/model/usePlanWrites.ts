import { useMutation, useQueryClient } from '@tanstack/vue-query'

import {
  changePlan,
  createPlan,
  deletePlan,
  hiringKeys,
  type HiringPlanBody,
} from '@/entities/workforce/hiring-plan'
import { refreshQueries } from '@/shared/lib/refresh'

export function useSavePlan() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: number | null; body: HiringPlanBody }) =>
      v.id === null ? createPlan(v.body) : changePlan(v.id, v.body),
    onSuccess: () => refreshQueries(queryClient, hiringKeys.all),
  })
}

export function useDeletePlan() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deletePlan(id),
    onSuccess: () => refreshQueries(queryClient, hiringKeys.all),
  })
}
