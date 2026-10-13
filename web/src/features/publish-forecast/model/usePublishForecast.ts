import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { forecastKeys, publishVersion } from '@/entities/forecast'

/** Make a draft the live forecast of its queue. The previous live one is archived by the server;
 * every list that shows versions is refreshed so both changes appear together. */
export function usePublishForecast() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (versionId: string) => publishVersion(versionId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: forecastKeys.all }),
  })
}
