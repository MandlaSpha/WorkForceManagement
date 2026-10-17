import { useMutation, useQueryClient } from '@tanstack/vue-query'

import {
  addActivity,
  removeActivity,
  schedulingKeys,
  type ShiftActivityBody,
} from '@/entities/scheduling'
import { refreshQueries } from '@/shared/lib/refresh'

/** Any change to a break or activity moves the plan's coverage too, so everything refreshes. */
export function useAddActivity() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ShiftActivityBody) => addActivity(body),
    onSuccess: () => refreshQueries(queryClient, schedulingKeys.all),
  })
}

export function useRemoveActivity() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => removeActivity(id),
    onSuccess: () => refreshQueries(queryClient, schedulingKeys.all),
  })
}
