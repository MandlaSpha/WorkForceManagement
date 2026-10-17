import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import { fetchMobilise, fetchTeams } from '../api/continuity'
import type { Scenario } from './types'

export const continuityKeys = { all: ['continuity'] as const }

export function useBackupTeams(queueId: MaybeRef<number | null>) {
  return useQuery({
    queryKey: computed(() => [...continuityKeys.all, 'teams', toValue(queueId)] as const),
    queryFn: () => fetchTeams(toValue(queueId)),
  })
}

export function useMobilise(
  queueId: MaybeRef<number | null>,
  day: MaybeRef<string>,
  scenario: MaybeRef<Scenario>,
  lostPct: MaybeRef<number>,
) {
  return useQuery({
    queryKey: computed(
      () =>
        [
          ...continuityKeys.all,
          'mobilise',
          toValue(queueId),
          toValue(day),
          toValue(scenario),
          toValue(lostPct),
        ] as const,
    ),
    queryFn: () =>
      fetchMobilise(toValue(queueId) as number, toValue(day), toValue(scenario), toValue(lostPct)),
    enabled: computed(() => toValue(queueId) !== null),
  })
}
