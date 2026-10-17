import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { capacityKeys } from '@/entities/workforce/capacity'
import { archiveVersion, discardVersion, forecastKeys } from '@/entities/forecast'
import { schedulingKeys } from '@/entities/scheduling'
import { refreshQueries } from '@/shared/lib/refresh'

/** Take a forecast out of use: delete a draft, or withdraw (archive) the live one. Withdrawing
 * leaves the queue with no live forecast, so the planner's coverage and the capacity view are
 * refreshed too: they would otherwise go on showing the withdrawn forecast's numbers. */
export function useRetireForecast() {
  const queryClient = useQueryClient()
  const refresh = () =>
    Promise.all([
      refreshQueries(queryClient, forecastKeys.all),
      refreshQueries(queryClient, schedulingKeys.all),
      refreshQueries(queryClient, capacityKeys.all),
    ])
  return {
    discard: useMutation({
      mutationFn: (input: { versionId: string; reason: string }) =>
        discardVersion(input.versionId, input.reason),
      onSuccess: refresh,
    }),
    archive: useMutation({
      mutationFn: (input: { versionId: string; reason: string }) =>
        archiveVersion(input.versionId, input.reason),
      onSuccess: refresh,
    }),
  }
}
