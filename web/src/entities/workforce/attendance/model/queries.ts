import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import { fetchAdherence, fetchMyAttendance } from '../api/attendance'

export const attendanceKeys = { all: ['attendance'] as const }

export function useAdherence(queueId: MaybeRef<number | null>, day: MaybeRef<string>) {
  return useQuery({
    queryKey: computed(
      () => [...attendanceKeys.all, 'day', toValue(queueId), toValue(day)] as const,
    ),
    queryFn: () => fetchAdherence(toValue(queueId) as number, toValue(day)),
    enabled: computed(() => toValue(queueId) !== null),
  })
}

export function useMyAttendance(day: MaybeRef<string>) {
  return useQuery({
    queryKey: computed(() => [...attendanceKeys.all, 'mine', toValue(day)] as const),
    queryFn: () => fetchMyAttendance(toValue(day)),
  })
}
