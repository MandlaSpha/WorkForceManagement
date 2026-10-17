import { api, unwrap } from '@/shared/api'

import type { ReportSchedule, ReportScheduleBody, ReportSchedulePatch } from '../model/types'

export async function fetchSchedules(): Promise<ReportSchedule[]> {
  return unwrap(await api.GET('/api/v1/reports/schedules'))
}

export async function createSchedule(body: ReportScheduleBody): Promise<ReportSchedule> {
  return unwrap(await api.POST('/api/v1/reports/schedules', { body }))
}

export async function changeSchedule(
  scheduleId: number,
  body: ReportSchedulePatch,
): Promise<ReportSchedule> {
  return unwrap(
    await api.PATCH('/api/v1/reports/schedules/{schedule_id}', {
      params: { path: { schedule_id: scheduleId } },
      body,
    }),
  )
}

export async function deleteSchedule(scheduleId: number): Promise<void> {
  unwrap(
    await api.DELETE('/api/v1/reports/schedules/{schedule_id}', {
      params: { path: { schedule_id: scheduleId } },
    }),
  )
}

export async function fetchAllowedDomains(): Promise<string[]> {
  return unwrap(await api.GET('/api/v1/reports/settings')).allowedDomains
}

export async function saveAllowedDomains(allowedDomains: string[]): Promise<string[]> {
  return unwrap(await api.PUT('/api/v1/reports/settings', { body: { allowedDomains } }))
    .allowedDomains
}
