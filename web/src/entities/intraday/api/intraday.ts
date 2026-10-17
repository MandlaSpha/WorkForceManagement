import { api, unwrap } from '@/shared/api'

import type { Intraday } from '../model/types'

export async function fetchIntraday(queueId: number, day: string): Promise<Intraday> {
  return unwrap(
    await api.GET('/api/v1/intraday', { params: { query: { queue_id: queueId, day } } }),
  )
}
