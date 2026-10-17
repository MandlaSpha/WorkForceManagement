import { api, unwrap } from '@/shared/api'

import type { Intraday, IntradaySuggestions } from '../model/types'

export async function fetchIntraday(queueId: number, day: string): Promise<Intraday> {
  return unwrap(
    await api.GET('/api/v1/intraday', { params: { query: { queue_id: queueId, day } } }),
  )
}

export async function fetchSuggestions(
  queueId: number,
  day: string,
  slot: number,
): Promise<IntradaySuggestions> {
  return unwrap(
    await api.GET('/api/v1/intraday/suggestions', {
      params: { query: { queue_id: queueId, day, slot } },
    }),
  )
}
