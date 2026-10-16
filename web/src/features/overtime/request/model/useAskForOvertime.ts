import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { askForOvertime, overtimeKeys, type OvertimeBody } from '@/entities/overtime'
import { refreshQueries } from '@/shared/lib/refresh'

export function useAskForOvertime() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: OvertimeBody) => askForOvertime(body),
    onSuccess: () => refreshQueries(queryClient, overtimeKeys.all),
  })
}
