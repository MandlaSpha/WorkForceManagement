import { useMutation, useQueryClient } from '@tanstack/vue-query'

import {
  fetchVersions,
  forecastKeys,
  startForecast,
  type ForecastVersion,
  type RunForecastRequest,
} from '@/entities/forecast'
import { waitForJob } from '@/entities/job'
import { ApiProblem } from '@/shared/api'
import { refreshQueries } from '@/shared/lib/refresh'

/** Run a forecast on the worker and wait for it; the new draft appears in every list that shows
 * versions. The button stays busy for the whole run, as it did when the call was inline. */
export function useRunForecast() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (request: RunForecastRequest): Promise<ForecastVersion> => {
      const job = await waitForJob(await startForecast(request))
      const versionId = (job.result as { versionId?: string } | null)?.versionId
      const version = (await fetchVersions(request.queueId)).find((v) => v.id === versionId)
      if (!version) {
        throw new ApiProblem({
          status: 502,
          code: 'job.no_result',
          title: 'No forecast was created',
          detail: 'The forecast finished but could not be found. Refresh and look in the list.',
        })
      }
      return version
    },
    onSuccess: () => refreshQueries(queryClient, forecastKeys.all),
  })
}
