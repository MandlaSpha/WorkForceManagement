import { api, unwrap } from '@/shared/api'

import type { MySchedule } from '../model/types'

export async function fetchMySchedule(): Promise<MySchedule> {
  return unwrap(await api.GET('/api/v1/people/my-schedule', { params: { query: {} } }))
}
