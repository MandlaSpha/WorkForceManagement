import { api, unwrap } from '@/shared/api'

import type { WorkloadBalance } from '../model/types'

export async function fetchBalance(day: string): Promise<WorkloadBalance> {
  return unwrap(await api.GET('/api/v1/utilisation/balance', { params: { query: { day } } }))
}
