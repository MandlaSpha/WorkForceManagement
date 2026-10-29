import { api, unwrap } from '@/shared/api'

import type { TeamOverview } from '../model/types'

export async function fetchTeamOverview(
  weekStart: string,
  managerId: number | null,
): Promise<TeamOverview> {
  return unwrap(
    await api.GET('/api/v1/people/team-overview', {
      params: {
        query: { week_start: weekStart, ...(managerId === null ? {} : { manager_id: managerId }) },
      },
    }),
  )
}
