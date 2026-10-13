import { useQuery } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'

import { monthRange } from '@/shared/lib/month'

import { fetchImports, fetchKpis, fetchMonths } from '../api/call-data'

/** Query keys. Anything that changes imported data invalidates these (see features/import). */
export const callDataKeys = {
  all: ['call-data'] as const,
  months: ['call-data', 'months'] as const,
  kpis: (month: string) => ['call-data', 'kpis', month] as const,
  imports: ['call-data', 'imports'] as const,
}

/** The months that have call data (`YYYY-MM`, oldest first). */
export function useMonths() {
  return useQuery({ queryKey: callDataKeys.months, queryFn: fetchMonths })
}

/** Service figures for one calendar month (`YYYY-MM`). Waits until a month is chosen. */
export function useKpis(month: Ref<string | null>) {
  return useQuery({
    queryKey: computed(() => callDataKeys.kpis(month.value ?? '')),
    queryFn: () => fetchKpis(monthRange(month.value as string)),
    enabled: computed(() => month.value !== null),
  })
}

export function useImports() {
  return useQuery({ queryKey: callDataKeys.imports, queryFn: fetchImports })
}
