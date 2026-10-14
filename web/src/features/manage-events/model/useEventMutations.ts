import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { createEvent, deleteEvent, forecastKeys, type EventRequest } from '@/entities/forecast'
import { refreshQueries } from '@/shared/lib/refresh'

/** Events only shape forecasts run afterwards, so only the calendar needs refreshing. */
export function useEventMutations() {
  const queryClient = useQueryClient()
  const refresh = () => refreshQueries(queryClient, [...forecastKeys.all, 'events'])
  return {
    create: useMutation({
      mutationFn: (body: EventRequest) => createEvent(body),
      onSuccess: refresh,
    }),
    remove: useMutation({ mutationFn: (id: number) => deleteEvent(id), onSuccess: refresh }),
  }
}
