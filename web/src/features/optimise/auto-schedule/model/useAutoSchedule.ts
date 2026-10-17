import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { waitForJob } from '@/entities/job'
import {
  previewAutoSchedule,
  schedulingKeys,
  startAutoSchedule,
  type AutoScheduleRequest,
  type AutoScheduleResult,
} from '@/entities/scheduling'
import { refreshQueries } from '@/shared/lib/refresh'

/** Preview changes nothing; applying runs on the worker and fills the roster, so it waits for the
 * job and then refreshes the roster and the plan. */
export function useAutoSchedule() {
  const queryClient = useQueryClient()
  return {
    preview: useMutation({ mutationFn: (body: AutoScheduleRequest) => previewAutoSchedule(body) }),
    apply: useMutation({
      mutationFn: async (body: AutoScheduleRequest): Promise<AutoScheduleResult> => {
        const job = await waitForJob(await startAutoSchedule(body))
        return job.result as unknown as AutoScheduleResult
      },
      onSuccess: () => refreshQueries(queryClient, schedulingKeys.all),
    }),
  }
}
