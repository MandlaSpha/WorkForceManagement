import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import { fetchScorecard } from '../api/scorecard'

export function useScorecard(from: MaybeRef<string>, to: MaybeRef<string>) {
  return useQuery({
    queryKey: computed(() => ['scorecard', toValue(from), toValue(to)] as const),
    queryFn: () => fetchScorecard(toValue(from), toValue(to)),
    enabled: computed(() => toValue(from) <= toValue(to)),
  })
}
