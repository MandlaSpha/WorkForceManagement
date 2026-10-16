import { useMutation, useQueryClient } from '@tanstack/vue-query'

import {
  applyRecommendation,
  schedulingKeys,
  type RecommendationApply,
} from '@/entities/scheduling'
import { refreshQueries } from '@/shared/lib/refresh'

/** Applying a suggestion changes the roster, so the plan and the list are worked out again. */
export function useApplyRecommendation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: RecommendationApply) => applyRecommendation(body),
    onSuccess: () => refreshQueries(queryClient, schedulingKeys.all),
  })
}
