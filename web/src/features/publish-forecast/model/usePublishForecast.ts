import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { capacityKeys } from '@/entities/workforce/capacity'
import { forecastKeys, publishVersion } from '@/entities/forecast'
import { schedulingKeys } from '@/entities/scheduling'
import { refreshQueries } from '@/shared/lib/refresh'

/** Make a draft the live forecast of its queue. The previous live one is archived by the server;
 * every list that shows versions is refreshed so both changes appear together. The planner's
 * coverage and the capacity view are worked out from the live forecast, so they are refreshed too:
 * showing the old forecast's figures for a moment after publishing would be a wrong answer. */
export function usePublishForecast() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (versionId: string) => publishVersion(versionId),
    onSuccess: () =>
      Promise.all([
        refreshQueries(queryClient, forecastKeys.all),
        refreshQueries(queryClient, schedulingKeys.all),
        refreshQueries(queryClient, capacityKeys.all),
      ]),
  })
}
