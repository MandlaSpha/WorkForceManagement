import { useMutation, useQueryClient } from '@tanstack/vue-query'

import {
  availabilityKeys,
  declareWindow,
  removeWindow,
  type AvailabilityBody,
} from '@/entities/availability'
import { refreshQueries } from '@/shared/lib/refresh'

export function useDeclareWindow() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: AvailabilityBody) => declareWindow(body),
    onSuccess: () => refreshQueries(queryClient, availabilityKeys.all),
  })
}

export function useRemoveWindow() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (windowId: number) => removeWindow(windowId),
    onSuccess: () => refreshQueries(queryClient, availabilityKeys.all),
  })
}
