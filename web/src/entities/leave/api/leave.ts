import { api, unwrap } from '@/shared/api'

import type {
  AwayLimit,
  Balances,
  Blackout,
  BlackoutBody,
  Decision,
  Impact,
  LeaveRequest,
  LeaveRequestBody,
  LeaveType,
} from '../model/types'

export async function fetchLeaveTypes(): Promise<LeaveType[]> {
  return unwrap(await api.GET('/api/v1/people/leave/types'))
}

export async function fetchBalances(year: number): Promise<Balances> {
  return unwrap(await api.GET('/api/v1/people/leave/balances', { params: { query: { year } } }))
}

export async function fetchRequests(status: string | null): Promise<LeaveRequest[]> {
  return unwrap(
    await api.GET('/api/v1/people/leave/requests', {
      params: { query: status === null ? {} : { status } },
    }),
  )
}

export async function applyForLeave(body: LeaveRequestBody): Promise<LeaveRequest> {
  return unwrap(await api.POST('/api/v1/people/leave/requests', { body }))
}

export type Decide = 'approve' | 'reject' | 'cancel'

export async function decideLeave(requestId: number, what: Decide): Promise<Decision> {
  const path = `/api/v1/people/leave/requests/{request_id}/${what}` as const
  return unwrap(await api.POST(path, { params: { path: { request_id: requestId } } }))
}

export async function fetchImpact(requestId: number): Promise<Impact> {
  return unwrap(
    await api.GET('/api/v1/people/leave/requests/{request_id}/impact', {
      params: { path: { request_id: requestId } },
    }),
  )
}

export async function setEntitlement(
  typeId: number,
  daysPerYear: number | null,
): Promise<LeaveType> {
  return unwrap(
    await api.PUT('/api/v1/people/leave/types/{type_id}', {
      params: { path: { type_id: typeId } },
      body: { daysPerYear },
    }),
  )
}

export async function fetchBlackouts(): Promise<Blackout[]> {
  return unwrap(await api.GET('/api/v1/people/leave/blackouts'))
}

export async function addBlackout(body: BlackoutBody): Promise<Blackout> {
  return unwrap(await api.POST('/api/v1/people/leave/blackouts', { body }))
}

export async function removeBlackout(blackoutId: number): Promise<void> {
  unwrap(
    await api.DELETE('/api/v1/people/leave/blackouts/{blackout_id}', {
      params: { path: { blackout_id: blackoutId } },
    }),
  )
}

export async function fetchAwayLimit(): Promise<AwayLimit> {
  return unwrap(await api.GET('/api/v1/people/leave/limit'))
}

export async function setAwayLimit(maxConcurrent: number | null): Promise<AwayLimit> {
  return unwrap(await api.PUT('/api/v1/people/leave/limit', { body: { maxConcurrent } }))
}
