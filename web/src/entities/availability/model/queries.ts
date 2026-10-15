import { useQuery } from '@tanstack/vue-query'

import { fetchAvailability } from '../api/availability'

/** Declaring or removing a window invalidates `all`. */
export const availabilityKeys = {
  all: ['availability'] as const,
  mine: ['availability', 'mine'] as const,
}

export function useAvailability() {
  return useQuery({
    queryKey: availabilityKeys.mine,
    queryFn: fetchAvailability,
    retry: false, // "not on the employee list" is an answer, not a glitch
  })
}
