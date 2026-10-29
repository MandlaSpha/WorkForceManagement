import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import { fetchTeamOverview } from '../api/team'

export const teamKeys = { all: ['team-overview'] as const }

export function useTeamOverview(weekStart: MaybeRef<string>, managerId: MaybeRef<number | null>) {
  return useQuery({
    queryKey: computed(() => [...teamKeys.all, toValue(weekStart), toValue(managerId)] as const),
    queryFn: () => fetchTeamOverview(toValue(weekStart), toValue(managerId)),
  })
}
