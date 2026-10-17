import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import { fetchCallDetail } from '../api/call-detail'

/** The call-detail figures of one month (`YYYY-MM`). Waits until a month is chosen. */
export function useCallDetail(month: MaybeRef<string | null>) {
  return useQuery({
    queryKey: computed(() => ['call-detail', toValue(month)] as const),
    queryFn: () => fetchCallDetail(toValue(month) as string),
    enabled: computed(() => toValue(month) !== null),
  })
}
