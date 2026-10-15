import { useQuery } from '@tanstack/vue-query'

import { fetchMySchedule } from '../api/mySchedule'

export const myScheduleKeys = { all: ['my-schedule'] as const }

export function useMySchedule() {
  return useQuery({
    queryKey: myScheduleKeys.all,
    queryFn: fetchMySchedule,
    retry: false, // "not on the employee list" is an answer, not a glitch
  })
}
