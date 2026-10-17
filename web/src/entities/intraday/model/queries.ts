import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import { fetchIntraday, fetchSuggestions } from '../api/intraday'

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

/** Who could be asked for overtime and which breaks could move, for ONE short half-hour. Asked
 * for only once a planner opens that alert. */
export function useSuggestions(
  queueId: MaybeRef<number | null>,
  day: MaybeRef<string>,
  slot: MaybeRef<number | null>,
) {
  return useQuery({
    queryKey: computed(
      () => ['intraday', 'suggestions', toValue(queueId), toValue(day), toValue(slot)] as const,
    ),
    queryFn: () =>
      fetchSuggestions(toValue(queueId) as number, toValue(day), toValue(slot) as number),
    enabled: computed(() => toValue(queueId) !== null && toValue(slot) !== null),
  })
}
