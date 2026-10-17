import { api, unwrap } from '@/shared/api'

import type { CallDetail } from '../model/detail-types'

export async function fetchCallDetail(month: string): Promise<CallDetail> {
  return unwrap(await api.GET('/api/v1/telephony/call-detail', { params: { query: { month } } }))
}
