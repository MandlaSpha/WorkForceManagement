import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { callDataKeys, uploadReport } from '@/entities/call-data'

/** Upload a report; on success every cached call-data answer is refreshed, so the dashboard and
 * the import list never show figures from before the import. */
export function useImportReport() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => uploadReport(file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: callDataKeys.all }),
  })
}
