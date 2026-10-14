import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { serviceDeskKeys, setProductiveMinutes } from '@/entities/service-desk'
import { refreshQueries } from '@/shared/lib/refresh'

export function useSetPoolMinutes() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (v: { poolId: number; minutes: number }) =>
      setProductiveMinutes(v.poolId, v.minutes),
    onSuccess: () => refreshQueries(queryClient, serviceDeskKeys.all),
  })
}
