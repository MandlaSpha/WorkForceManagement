import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { createShift, deleteShift, schedulingKeys, type ShiftRequest } from '@/entities/scheduling'
import { refreshQueries } from '@/shared/lib/refresh'

export function useShiftMutations() {
  const queryClient = useQueryClient()
  const refresh = () => refreshQueries(queryClient, schedulingKeys.all)
  return {
    create: useMutation({
      mutationFn: (body: ShiftRequest) => createShift(body),
      onSuccess: refresh,
    }),
    remove: useMutation({ mutationFn: (id: number) => deleteShift(id), onSuccess: refresh }),
  }
}
