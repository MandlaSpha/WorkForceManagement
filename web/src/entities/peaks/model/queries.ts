import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import { fetchPeaks } from '../api/peaks'

export function usePeaks(
  queueId: MaybeRef<number | null>,
  from: MaybeRef<string>,
  to: MaybeRef<string>,
) {
  return useQuery({
    queryKey: computed(() => ['peaks', toValue(queueId), toValue(from), toValue(to)] as const),
    queryFn: () => fetchPeaks(toValue(queueId) as number, toValue(from), toValue(to)),
    enabled: computed(() => toValue(queueId) !== null && toValue(from) <= toValue(to)),
  })
}
