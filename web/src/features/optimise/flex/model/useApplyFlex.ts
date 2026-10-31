import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { applyFlex, schedulingKeys, type FlexApply } from '@/entities/scheduling'
import { refreshQueries } from '@/shared/lib/refresh'

/** Borrowing someone moves a shift between two queues, so every plan and list is worked out again. */
export function useApplyFlex() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: FlexApply) => applyFlex(body),
    onSuccess: () => refreshQueries(queryClient, schedulingKeys.all),
  })
}
