import { useQuery } from '@tanstack/vue-query'

import { fetchInbox } from '../api/notification'

export const notificationKeys = { all: ['notifications'] as const }

/** The inbox, looked at again every minute and whenever the window is focused, so a message
 * sent while someone is working shows up without a refresh. */
export function useInbox() {
  return useQuery({
    queryKey: notificationKeys.all,
    queryFn: fetchInbox,
    refetchInterval: 60_000,
    retry: false,
  })
}
