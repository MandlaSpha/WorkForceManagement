import { useQuery } from '@tanstack/vue-query'

import { fetchWellbeing } from '../api/wellbeing'

export const wellbeingKeys = { all: ['wellbeing'] as const }

export function useWellbeing() {
  return useQuery({ queryKey: wellbeingKeys.all, queryFn: fetchWellbeing })
}
