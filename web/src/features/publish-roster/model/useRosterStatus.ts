import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { publishRoster, reopenRoster, schedulingKeys } from '@/entities/scheduling'

/** Publish a week, or return it to draft so it can be changed. Both refresh the roster and plan. */
export function useRosterStatus() {
  const queryClient = useQueryClient()
  const refresh = () => queryClient.invalidateQueries({ queryKey: schedulingKeys.all })
  return {
    publish: useMutation({
      mutationFn: (v: { queueId: number; weekStart: string }) =>
        publishRoster(v.queueId, v.weekStart),
      onSuccess: refresh,
    }),
    reopen: useMutation({
      mutationFn: (v: { queueId: number; weekStart: string }) =>
        reopenRoster(v.queueId, v.weekStart),
      onSuccess: refresh,
    }),
  }
}
