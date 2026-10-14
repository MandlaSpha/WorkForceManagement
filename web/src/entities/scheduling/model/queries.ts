import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import { fetchEmployees, fetchPlan, fetchRoster, fetchShifts } from '../api/scheduling'

/** Query keys. Any change to shifts, people or the roster invalidates `all`, so the roster, the
 * plan and the lists never disagree. */
export const schedulingKeys = {
  all: ['scheduling'] as const,
  shifts: ['scheduling', 'shifts'] as const,
  employees: (queueId: number | null) => ['scheduling', 'employees', queueId] as const,
  roster: (queueId: number, week: string) => ['scheduling', 'roster', queueId, week] as const,
  plan: (queueId: number, week: string) => ['scheduling', 'plan', queueId, week] as const,
}

export function useShifts() {
  return useQuery({ queryKey: schedulingKeys.shifts, queryFn: fetchShifts })
}

export function useEmployees(queueId: MaybeRef<number | null> = null) {
  return useQuery({
    queryKey: computed(() => schedulingKeys.employees(toValue(queueId))),
    queryFn: () => fetchEmployees(toValue(queueId)),
  })
}

export function useRoster(queueId: MaybeRef<number | null>, week: MaybeRef<string>) {
  return useQuery({
    queryKey: computed(() => schedulingKeys.roster(toValue(queueId) ?? 0, toValue(week))),
    queryFn: () => fetchRoster(toValue(queueId) as number, toValue(week)),
    enabled: computed(() => toValue(queueId) !== null),
  })
}

export function usePlan(queueId: MaybeRef<number | null>, week: MaybeRef<string>) {
  return useQuery({
    queryKey: computed(() => schedulingKeys.plan(toValue(queueId) ?? 0, toValue(week))),
    queryFn: () => fetchPlan(toValue(queueId) as number, toValue(week)),
    enabled: computed(() => toValue(queueId) !== null),
  })
}
