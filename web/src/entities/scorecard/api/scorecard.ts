import { api, unwrap } from '@/shared/api'

import type { Scorecard } from '../model/types'

export async function fetchScorecard(from: string, to: string): Promise<Scorecard> {
  return unwrap(
    await api.GET('/api/v1/insight/scorecard', {
      params: { query: { date_from: from, date_to: to } },
    }),
  )
}
