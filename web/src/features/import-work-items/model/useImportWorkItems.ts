import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { importWorkItems, serviceDeskKeys } from '@/entities/service-desk'
import { refreshQueries } from '@/shared/lib/refresh'

export function useImportWorkItems() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => importWorkItems(file),
    onSuccess: () => refreshQueries(queryClient, serviceDeskKeys.all),
  })
}
