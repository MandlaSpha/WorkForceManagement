import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { bookStandby, cancelStandby, overtimeKeys, recordCallOut } from '@/entities/overtime'
import { refreshQueries } from '@/shared/lib/refresh'

export function useBookStandby() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (v: { employeeId: number; day: string }) => bookStandby(v.employeeId, v.day),
    onSuccess: () => refreshQueries(queryClient, overtimeKeys.all),
  })
}

export function useCancelStandby() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (standbyId: number) => cancelStandby(standbyId),
    onSuccess: () => refreshQueries(queryClient, overtimeKeys.all),
  })
}

export function useRecordCallOut() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (v: { standbyId: number; minutes: number }) =>
      recordCallOut(v.standbyId, v.minutes),
    onSuccess: () => refreshQueries(queryClient, overtimeKeys.all),
  })
}
