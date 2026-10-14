import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import {
  fetchAccuracy,
  fetchBacktest,
  fetchEvents,
  fetchIntervals,
  fetchTuning,
  fetchVersions,
  type TuningTrial,
} from '../api/forecast'

/** Query keys. Running or publishing a forecast invalidates `all`. */
export const forecastKeys = {
  all: ['forecast'] as const,
  versions: (queueId: number | null) => ['forecast', 'versions', queueId] as const,
  intervals: (versionId: string) => ['forecast', 'intervals', versionId] as const,
  events: (queueId: number | null) => ['forecast', 'events', queueId] as const,
  tuning: (queueId: number) => ['forecast', 'tuning', queueId] as const,
  backtest: (queueId: number, trial: TuningTrial) =>
    ['forecast', 'backtest', queueId, trial] as const,
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

export function useEvents(queueId: MaybeRef<number | null>) {
  return useQuery({
    queryKey: computed(() => forecastKeys.events(toValue(queueId))),
    queryFn: () => fetchEvents(toValue(queueId)),
  })
}

export function useTuning(queueId: MaybeRef<number | null>) {
  return useQuery({
    queryKey: computed(() => forecastKeys.tuning(toValue(queueId) ?? 0)),
    queryFn: () => fetchTuning(toValue(queueId) as number),
    enabled: computed(() => toValue(queueId) !== null),
  })
}

/** The back-test of a tuning that has not been saved. Saving a tuning refreshes it (it is under
 * `forecastKeys.all`), so "the saved one" it is compared with is never stale. */
export function useBacktest(queueId: MaybeRef<number | null>, trial: MaybeRef<TuningTrial>) {
  return useQuery({
    queryKey: computed(() => forecastKeys.backtest(toValue(queueId) ?? 0, toValue(trial))),
    queryFn: () => fetchBacktest(toValue(queueId) as number, toValue(trial)),
    enabled: computed(() => toValue(queueId) !== null),
  })
}
