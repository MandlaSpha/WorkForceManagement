import { api, unwrap } from '@/shared/api'

import type { Shrinkage } from '../model/types'

/** `month` is any day of the month, as YYYY-MM-DD. */
export async function fetchShrinkage(month: string): Promise<Shrinkage> {
  return unwrap(await api.GET('/api/v1/people/shrinkage', { params: { query: { month } } }))
}
