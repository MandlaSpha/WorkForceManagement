import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import { fetchMyQuality, fetchQualityPerson, fetchQualityTeam } from '../api/quality'

/** Importing a file invalidates `all`. */
export const qualityKeys = { all: ['quality'] as const }

export function useQualityTeam(days: MaybeRef<number>, enabled: MaybeRef<boolean>) {
  return useQuery({
    queryKey: computed(() => [...qualityKeys.all, 'team', toValue(days)] as const),
    queryFn: () => fetchQualityTeam(toValue(days)),
    enabled: computed(() => toValue(enabled)),
  })
}

export function useQualityPerson(employeeId: MaybeRef<number | null>, days: MaybeRef<number>) {
  return useQuery({
    queryKey: computed(
      () => [...qualityKeys.all, 'person', toValue(employeeId), toValue(days)] as const,
    ),
    queryFn: () => fetchQualityPerson(toValue(employeeId) as number, toValue(days)),
    enabled: computed(() => toValue(employeeId) !== null),
  })
}

export function useMyQuality(days: MaybeRef<number>, enabled: MaybeRef<boolean>) {
  return useQuery({
    queryKey: computed(() => [...qualityKeys.all, 'mine', toValue(days)] as const),
    queryFn: () => fetchMyQuality(toValue(days)),
    enabled: computed(() => toValue(enabled)),
    retry: false, // a person who is not on the employee list is a plain answer, not a glitch
  })
}
