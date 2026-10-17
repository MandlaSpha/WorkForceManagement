import { api, unwrap } from '@/shared/api'

import type { Peaks } from '../model/types'

export async function fetchPeaks(queueId: number, from: string, to: string): Promise<Peaks> {
  return unwrap(
    await api.GET('/api/v1/telephony/peaks', {
      params: { query: { queue_id: queueId, date_from: from, date_to: to } },
    }),
  )
}
