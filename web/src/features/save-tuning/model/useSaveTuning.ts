import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { forecastKeys, saveTuning, type TuningRequest } from '@/entities/forecast'

/** Saving a tuning changes the forecasts run afterwards, the accuracy measured with it and what a
 * back-test is compared with, so everything under the forecast keys is refreshed. */
export function useSaveTuning() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: TuningRequest) => saveTuning(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: forecastKeys.all }),
  })
}
