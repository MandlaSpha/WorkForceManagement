import { api, unwrap } from '@/shared/api'

import type { BackupTeam, Mobilise, Scenario } from '../model/types'

export async function fetchTeams(queueId: number | null): Promise<BackupTeam[]> {
  return unwrap(
    await api.GET('/api/v1/continuity/teams', {
      params: { query: queueId === null ? {} : { queue_id: queueId } },
    }),
  )
}

export async function fetchMobilise(
  queueId: number,
  day: string,
  scenario: Scenario,
  lostPct: number,
): Promise<Mobilise> {
  return unwrap(
    await api.GET('/api/v1/continuity/mobilise', {
      params: { query: { queue_id: queueId, day, scenario, lost_pct: lostPct } },
    }),
  )
}

export async function createTeam(queueId: number, name: string): Promise<BackupTeam> {
  return unwrap(await api.POST('/api/v1/continuity/teams', { body: { queueId, name } }))
}

export async function deleteTeam(teamId: number): Promise<void> {
  unwrap(
    await api.DELETE('/api/v1/continuity/teams/{team_id}', {
      params: { path: { team_id: teamId } },
    }),
  )
}

export async function addMember(teamId: number, employeeId: number): Promise<BackupTeam> {
  return unwrap(
    await api.POST('/api/v1/continuity/teams/{team_id}/members', {
      params: { path: { team_id: teamId } },
      body: { employeeId },
    }),
  )
}

export async function removeMember(teamId: number, employeeId: number): Promise<void> {
  unwrap(
    await api.DELETE('/api/v1/continuity/teams/{team_id}/members/{employee_id}', {
      params: { path: { team_id: teamId, employee_id: employeeId } },
    }),
  )
}
