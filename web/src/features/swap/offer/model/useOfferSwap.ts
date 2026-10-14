import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { offerSwap, swapKeys, type SwapBody } from '@/entities/swap'
import { refreshQueries } from '@/shared/lib/refresh'

export function useOfferSwap() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: SwapBody) => offerSwap(body),
    onSuccess: () => refreshQueries(queryClient, swapKeys.all),
  })
}
