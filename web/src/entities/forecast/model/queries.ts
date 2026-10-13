import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import { fetchAccuracy, fetchIntervals, fetchVersions } from '../api/forecast'

/** Query keys. Running or publishing a forecast invalidates `all`. */
export const forecastKeys = {
  all: ['forecast'] as const,
  versions: (queueId: number | null) => ['forecast', 'versions', queueId] as const,
  intervals: (versionId: string) => ['forecast', 'intervals', versionId] as const,
  accuracy: (queueId: number) => ['forecast', 'accuracy', queueId] as const,
}

export function useVersions(queueId: MaybeRef<number | null>) {
  return useQuery({
    queryKey: computed(() => forecastKeys.versions(toValue(queueId))),
    queryFn: () => fetchVersions(toValue(queueId)),
  })
}

export function useIntervals(versionId: MaybeRef<string | null>) {
  return useQuery({
    queryKey: computed(() => forecastKeys.intervals(toValue(versionId) ?? '')),
    queryFn: () => fetchIntervals(toValue(versionId) as string),
    enabled: computed(() => toValue(versionId) !== null),
  })
}

export function useAccuracy(queueId: MaybeRef<number | null>) {
  return useQuery({
    queryKey: computed(() => forecastKeys.accuracy(toValue(queueId) ?? 0)),
    queryFn: () => fetchAccuracy(toValue(queueId) as number),
    enabled: computed(() => toValue(queueId) !== null),
  })
}
