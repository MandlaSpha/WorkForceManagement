import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { overtimeKeys, saveBudget, saveStandbyAllowance } from '@/entities/overtime'
import { refreshQueries } from '@/shared/lib/refresh'

export function useSaveAllowance() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (amount: number) => saveStandbyAllowance(amount),
    onSuccess: () => refreshQueries(queryClient, overtimeKeys.all),
  })
}

export function useSaveBudget() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (v: { month: string; amount: number | null }) => saveBudget(v.month, v.amount),
    onSuccess: () => refreshQueries(queryClient, overtimeKeys.all),
  })
}
