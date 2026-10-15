import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { swapKeys, takeSwap, type Swap } from '@/entities/swap'
import { refreshQueries } from '@/shared/lib/refresh'

/** `reported` is told BEFORE the refresh, because the refresh takes the request off the board and
 * the component that asked goes with it. */
export function useTakeSwap(reported?: (swap: Swap) => void) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (v: { swapId: number; assignmentId: number }) => takeSwap(v.swapId, v.assignmentId),
    onSuccess: async (swap) => {
      reported?.(swap)
      await refreshQueries(queryClient, swapKeys.all)
    },
  })
}
