import { api, unwrap } from '@/shared/api'

import type {
  Credential,
  CredentialInput,
  Requirement,
  RequirementInput,
  SkillGap,
} from '../model/types'

export async function fetchCredentials(employeeId: number | null): Promise<Credential[]> {
  return unwrap(
    await api.GET('/api/v1/skills/credentials', {
      params: { query: employeeId === null ? {} : { employee_id: employeeId } },
    }),
  )
}

export async function saveCredentials(
  employeeId: number,
  credentials: CredentialInput[],
): Promise<Credential[]> {
  return unwrap(
    await api.PUT('/api/v1/skills/employees/{employee_id}/credentials', {
      params: { path: { employee_id: employeeId } },
      body: { credentials },
    }),
  )
}

export async function fetchRequirements(queueId: number): Promise<Requirement[]> {
  return unwrap(
    await api.GET('/api/v1/skills/requirements', { params: { query: { queue_id: queueId } } }),
  )
}

export async function saveRequirements(
  queueId: number,
  requirements: RequirementInput[],
): Promise<Requirement[]> {
  return unwrap(
    await api.PUT('/api/v1/skills/queues/{queue_id}/requirements', {
      params: { path: { queue_id: queueId } },
      body: { requirements },
    }),
  )
}

export async function fetchGaps(start: string, days: number): Promise<SkillGap[]> {
  return unwrap(await api.GET('/api/v1/skills/gaps', { params: { query: { start, days } } }))
}
