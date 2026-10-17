import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { overtimeKeys, recordWorked } from '@/entities/overtime'
import { refreshQueries } from '@/shared/lib/refresh'

export function useRecordWorked() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (v: { requestId: number; minutes: number }) => recordWorked(v.requestId, v.minutes),
    onSuccess: () => refreshQueries(queryClient, overtimeKeys.all),
  })
}
