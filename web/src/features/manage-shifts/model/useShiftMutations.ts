import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { createShift, deleteShift, schedulingKeys, type ShiftRequest } from '@/entities/scheduling'

export function useShiftMutations() {
  const queryClient = useQueryClient()
  const refresh = () => queryClient.invalidateQueries({ queryKey: schedulingKeys.all })
  return {
    create: useMutation({
      mutationFn: (body: ShiftRequest) => createShift(body),
      onSuccess: refresh,
    }),
    remove: useMutation({ mutationFn: (id: number) => deleteShift(id), onSuccess: refresh }),
  }
}
