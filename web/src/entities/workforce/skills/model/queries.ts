import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import { fetchCredentials, fetchGaps, fetchRequirements } from '../api/skills'

export const skillKeys = { all: ['skills'] as const }

export function useCredentials(employeeId: MaybeRef<number | null>) {
  return useQuery({
    queryKey: computed(() => [...skillKeys.all, 'credentials', toValue(employeeId)] as const),
    queryFn: () => fetchCredentials(toValue(employeeId)),
  })
}

export function useRequirements(queueId: MaybeRef<number | null>) {
  return useQuery({
    queryKey: computed(() => [...skillKeys.all, 'requirements', toValue(queueId)] as const),
    queryFn: () => fetchRequirements(toValue(queueId) as number),
    enabled: computed(() => toValue(queueId) !== null),
  })
}

export function useGaps(start: MaybeRef<string>, days: number, enabled: MaybeRef<boolean> = true) {
  return useQuery({
    queryKey: computed(() => [...skillKeys.all, 'gaps', toValue(start), days] as const),
    queryFn: () => fetchGaps(toValue(start), days),
    enabled,
  })
}
