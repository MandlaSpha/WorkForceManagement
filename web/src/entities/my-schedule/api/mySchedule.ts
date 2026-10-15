import { api, unwrap } from '@/shared/api'

import type { MySchedule } from '../model/types'

export async function fetchMySchedule(from: string, to: string): Promise<MySchedule> {
  return unwrap(
    await api.GET('/api/v1/people/my-schedule', {
      params: { query: { from_date: from, to_date: to } },
    }),
  )
}
