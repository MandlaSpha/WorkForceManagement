import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { importEmployees, schedulingKeys } from '@/entities/scheduling'
import { refreshQueries } from '@/shared/lib/refresh'

/** Checking a file changes nothing; importing it does, so only that refreshes the lists. */
export function useImportEmployees() {
  const queryClient = useQueryClient()
  return {
    check: useMutation({ mutationFn: (file: File) => importEmployees(file, true) }),
    run: useMutation({
      mutationFn: (file: File) => importEmployees(file, false),
      onSuccess: () => refreshQueries(queryClient, schedulingKeys.all),
    }),
  }
}
