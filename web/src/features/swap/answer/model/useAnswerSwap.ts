import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { schedulingKeys } from '@/entities/scheduling'
import { answerSwap, swapKeys, type Swap, type SwapAnswer } from '@/entities/swap'
import { refreshQueries } from '@/shared/lib/refresh'

/** An approved swap changes the roster, so the roster views refresh with the swap lists.
 *
 * `reported` is told the outcome BEFORE the refresh, because the refresh moves the swap out of
 * the list it was in and takes the component that asked with it. */
export function useAnswerSwap(reported?: (what: SwapAnswer, swap: Swap) => void) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (v: { swapId: number; what: SwapAnswer }) => answerSwap(v.swapId, v.what),
    onSuccess: async (swap, v) => {
      reported?.(v.what, swap)
      await refreshQueries(queryClient, swapKeys.all, schedulingKeys.all)
    },
  })
}
