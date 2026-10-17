import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { moveActivity, schedulingKeys } from '@/entities/scheduling'
import { refreshQueries } from '@/shared/lib/refresh'

/** Moving a break changes the plan's cover, so the day, its suggestions and the roster refresh. */
export function useMoveBreak() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (move: { activityId: number; startTime: string }) =>
      moveActivity(move.activityId, move.startTime),
    onSuccess: () => refreshQueries(queryClient, ['intraday'], schedulingKeys.all),
  })
}
