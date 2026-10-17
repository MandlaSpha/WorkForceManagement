import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import { fetchCapacity } from '../api/capacity'

/** Changing the limits invalidates `all`, so every capacity view agrees. */
export const capacityKeys = {
  all: ['capacity'] as const,
  view: (weekStart: string, weeks: number) => ['capacity', weekStart, weeks] as const,
}

export function useCapacity(weekStart: MaybeRef<string>, weeks: MaybeRef<number>) {
  return useQuery({
    queryKey: computed(() => capacityKeys.view(toValue(weekStart), toValue(weeks))),
    queryFn: () => fetchCapacity(toValue(weekStart), toValue(weeks)),
  })
}
