import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { qualityKeys, uploadQuality } from '@/entities/workforce/quality'
import { refreshQueries } from '@/shared/lib/refresh'

/** Upload a quality file; on success every cached quality answer is refreshed. */
export function useImportQuality() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => uploadQuality(file),
    onSuccess: () => refreshQueries(queryClient, qualityKeys.all),
  })
}
