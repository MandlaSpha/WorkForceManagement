import { useMutation, useQueryClient } from '@tanstack/vue-query'

import {
  changeSchedule,
  createSchedule,
  deleteSchedule,
  reportKeys,
  type ReportSchedulePatch,
  type ReportScheduleBody,
} from '@/entities/report-schedule'
import { refreshQueries } from '@/shared/lib/refresh'

export function useCreateSchedule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ReportScheduleBody) => createSchedule(body),
    onSuccess: () => refreshQueries(queryClient, reportKeys.all),
  })
}

export function useChangeSchedule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: number; body: ReportSchedulePatch }) => changeSchedule(v.id, v.body),
    onSuccess: () => refreshQueries(queryClient, reportKeys.all),
  })
}

export function useDeleteSchedule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deleteSchedule(id),
    onSuccess: () => refreshQueries(queryClient, reportKeys.all),
  })
}
