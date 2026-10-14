import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { capacityKeys, saveLimits, type LimitsRequest } from '@/entities/capacity'

export function useSaveLimits() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: LimitsRequest) => saveLimits(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: capacityKeys.all }),
  })
}
