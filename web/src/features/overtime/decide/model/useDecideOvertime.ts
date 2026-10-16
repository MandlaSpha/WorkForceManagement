import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { decideOvertime, overtimeKeys, type Decide } from '@/entities/overtime'
import { refreshQueries } from '@/shared/lib/refresh'

export function useDecideOvertime() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (v: { requestId: number; what: Decide }) => decideOvertime(v.requestId, v.what),
    onSuccess: () => refreshQueries(queryClient, overtimeKeys.all),
  })
}
