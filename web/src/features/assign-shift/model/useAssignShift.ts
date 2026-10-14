import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { assignShift, schedulingKeys, type AssignRequest } from '@/entities/scheduling'
import { refreshQueries } from '@/shared/lib/refresh'

/** Put a person on a shift (or clear it). The roster and the plan are both refreshed, so the
 * variance moves the moment the shift does. */
export function useAssignShift() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (request: AssignRequest) => assignShift(request),
    onSuccess: () => refreshQueries(queryClient, schedulingKeys.all),
  })
}
