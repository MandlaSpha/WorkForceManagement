import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import { fetchShrinkage } from '../api/shrinkage'

export function useShrinkage(month: MaybeRef<string>) {
  return useQuery({
    queryKey: computed(() => ['shrinkage', toValue(month)] as const),
    queryFn: () => fetchShrinkage(toValue(month)),
  })
}
