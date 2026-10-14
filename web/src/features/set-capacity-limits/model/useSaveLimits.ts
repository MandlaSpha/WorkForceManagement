import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { capacityKeys, saveLimits, type LimitsRequest } from '@/entities/capacity'
import { refreshQueries } from '@/shared/lib/refresh'

export function useSaveLimits() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: LimitsRequest) => saveLimits(body),
    onSuccess: () => refreshQueries(queryClient, capacityKeys.all),
  })
}
