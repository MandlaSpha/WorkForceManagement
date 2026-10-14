import { api, unwrap } from '@/shared/api'

import type { Capacity, Limits, LimitsRequest } from '../model/types'

export async function fetchCapacity(weekStart: string, weeks: number): Promise<Capacity> {
  return unwrap(
    await api.GET('/api/v1/capacity', { params: { query: { week_start: weekStart, weeks } } }),
  )
}

export async function saveLimits(body: LimitsRequest): Promise<Limits> {
  return unwrap(await api.PUT('/api/v1/capacity/limits', { body }))
}
