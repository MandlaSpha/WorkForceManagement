import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRef } from 'vue'

import { fetchMySchedule } from '../api/mySchedule'

export const myScheduleKeys = {
  all: ['my-schedule'] as const,
  range: (from: string, to: string) => ['my-schedule', from, to] as const,
}

export function useMySchedule(from: MaybeRef<string>, to: MaybeRef<string>) {
  return useQuery({
    queryKey: computed(() => myScheduleKeys.range(toValue(from), toValue(to))),
    queryFn: () => fetchMySchedule(toValue(from), toValue(to)),
    retry: false, // "not on the employee list" is an answer, not a glitch
  })
}
