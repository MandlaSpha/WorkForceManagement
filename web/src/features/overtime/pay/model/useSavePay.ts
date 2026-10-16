import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { overtimeKeys, savePay, type PayBody } from '@/entities/overtime'
import { refreshQueries } from '@/shared/lib/refresh'

export function useSavePay() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (v: { employeeId: number; body: PayBody }) => savePay(v.employeeId, v.body),
    onSuccess: () => refreshQueries(queryClient, overtimeKeys.all),
  })
}
