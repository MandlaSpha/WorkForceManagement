import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import { fetchIntraday } from '../api/intraday'

const MINUTE_MS = 60_000

/** The day is asked for again every minute: calls are imported as the day goes on. */
export function useIntraday(queueId: MaybeRef<number | null>, day: MaybeRef<string>) {
  return useQuery({
    queryKey: computed(() => ['intraday', toValue(queueId), toValue(day)] as const),
    queryFn: () => fetchIntraday(toValue(queueId) as number, toValue(day)),
    enabled: computed(() => toValue(queueId) !== null),
    refetchInterval: MINUTE_MS,
  })
}
