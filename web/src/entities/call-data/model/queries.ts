import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef, type Ref } from 'vue'

import { monthRange } from '@/shared/lib/month'

import { fetchImports, fetchKpis, fetchMonths, fetchQueues } from '../api/call-data'

/** Query keys. Anything that changes imported data invalidates these (see features/import). */
export const callDataKeys = {
  all: ['call-data'] as const,
  months: ['call-data', 'months'] as const,
  kpis: (month: string) => ['call-data', 'kpis', month] as const,
  imports: ['call-data', 'imports'] as const,
  queues: ['call-data', 'queues'] as const,
}

/** The months that have call data (`YYYY-MM`, oldest first). */
export function useMonths(enabled: MaybeRef<boolean> = true) {
  return useQuery({
    queryKey: callDataKeys.months,
    queryFn: fetchMonths,
    enabled: computed(() => toValue(enabled)),
  })
}

/** Service figures for one calendar month (`YYYY-MM`). Waits until a month is chosen. */
export function useKpis(month: Ref<string | null>) {
  return useQuery({
    queryKey: computed(() => callDataKeys.kpis(month.value ?? '')),
    queryFn: () => fetchKpis(monthRange(month.value as string)),
    enabled: computed(() => month.value !== null),
  })
}

/** The queues this role may see, with their staffing assumptions. */
export function useQueues(enabled: MaybeRef<boolean> = true) {
  return useQuery({
    queryKey: callDataKeys.queues,
    queryFn: fetchQueues,
    enabled: computed(() => toValue(enabled)),
  })
}

export function useImports() {
  return useQuery({ queryKey: callDataKeys.imports, queryFn: fetchImports })
}
