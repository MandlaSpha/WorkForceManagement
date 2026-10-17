import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { attendanceKeys, uploadStates } from '@/entities/workforce/attendance'
import { refreshQueries } from '@/shared/lib/refresh'

/** Upload a state file; on success every cached adherence answer is refreshed. */
export function useImportStates() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => uploadStates(file),
    onSuccess: () => refreshQueries(queryClient, attendanceKeys.all),
  })
}
