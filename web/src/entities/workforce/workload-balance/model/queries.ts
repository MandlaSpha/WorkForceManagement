import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import { fetchBalance } from '../api/balance'

export function useBalance(day: MaybeRef<string>) {
  return useQuery({
    queryKey: computed(() => ['workload-balance', toValue(day)] as const),
    queryFn: () => fetchBalance(toValue(day)),
  })
}
