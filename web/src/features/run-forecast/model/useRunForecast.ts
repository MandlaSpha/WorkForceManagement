import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { forecastKeys, runForecast, type RunForecastRequest } from '@/entities/forecast'
import { refreshQueries } from '@/shared/lib/refresh'

/** Run the baseline forecast; the new draft appears in every list that shows versions. */
export function useRunForecast() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (request: RunForecastRequest) => runForecast(request),
    onSuccess: () => refreshQueries(queryClient, forecastKeys.all),
  })
}
