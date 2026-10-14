import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { applyForLeave, leaveKeys, type LeaveRequestBody } from '@/entities/leave'
import { refreshQueries } from '@/shared/lib/refresh'

export function useApplyLeave() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: LeaveRequestBody) => applyForLeave(body),
    onSuccess: () => refreshQueries(queryClient, leaveKeys.all),
  })
}
