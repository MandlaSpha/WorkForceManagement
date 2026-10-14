import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { callDataKeys, saveQueueSettings, type QueueSettings } from '@/entities/call-data'

/** Save and confirm a queue's staffing assumptions. Screens that show the "unconfirmed" warning
 * refresh from the queue list. */
export function useSaveQueueSettings(queueId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (settings: QueueSettings) => saveQueueSettings(queueId, settings),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: callDataKeys.queues }),
  })
}
