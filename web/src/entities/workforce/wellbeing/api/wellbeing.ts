import { api, unwrap } from '@/shared/api'

import type { Wellbeing } from '../model/types'

export async function fetchWellbeing(): Promise<Wellbeing> {
  return unwrap(await api.GET('/api/v1/wellbeing/flags'))
}
