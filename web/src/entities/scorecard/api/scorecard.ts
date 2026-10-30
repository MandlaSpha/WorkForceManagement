import { api, unwrap } from '@/shared/api'

import type { Scorecard } from '../model/types'

export async function fetchScorecard(from: string, to: string): Promise<Scorecard> {
  return unwrap(
    await api.GET('/api/v1/insight/scorecard', {
      params: { query: { date_from: from, date_to: to } },
    }),
  )
}

/** The address of the CSV of the scorecard for a range. */
export function scorecardCsvUrl(from: string, to: string): string {
  return `/api/v1/insight/scorecard.csv?date_from=${from}&date_to=${to}`
}
