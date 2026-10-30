import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { decideLeave, leaveKeys, type Decide, type Decision } from '@/entities/leave'
import { schedulingKeys } from '@/entities/scheduling'
import { refreshQueries } from '@/shared/lib/refresh'

/** Cancelling or deciding changes the roster too (shifts come off or go back), so the planner and
 * roster views are refreshed with the leave lists.
 *
 * `reported` is told the outcome BEFORE the refresh: the refresh drops the request from the waiting
 * list and with it the component that asked, and a callback given to `mutate()` is not run once
 * that component has gone. */
export function useDecideLeave(reported?: (decision: Decision) => void) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (v: { requestId: number; what: Decide; reason?: string }) =>
      decideLeave(v.requestId, v.what, v.reason),
    onSuccess: async (decision) => {
      reported?.(decision)
      await refreshQueries(queryClient, leaveKeys.all, schedulingKeys.all)
    },
  })
}
