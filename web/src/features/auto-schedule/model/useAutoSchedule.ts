import { useMutation, useQueryClient } from '@tanstack/vue-query'

import {
  applyAutoSchedule,
  previewAutoSchedule,
  schedulingKeys,
  type AutoScheduleRequest,
} from '@/entities/scheduling'
import { refreshQueries } from '@/shared/lib/refresh'

/** Preview changes nothing; applying fills the roster, so it refreshes the roster and the plan. */
export function useAutoSchedule() {
  const queryClient = useQueryClient()
  return {
    preview: useMutation({ mutationFn: (body: AutoScheduleRequest) => previewAutoSchedule(body) }),
    apply: useMutation({
      mutationFn: (body: AutoScheduleRequest) => applyAutoSchedule(body),
      onSuccess: () => refreshQueries(queryClient, schedulingKeys.all),
    }),
  }
}
