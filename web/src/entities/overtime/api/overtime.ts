import { api, unwrap } from '@/shared/api'

import type {
  Overtime,
  OvertimeBody,
  OvertimeStatus,
  OvertimeSummary,
  PayBody,
  PayStatus,
  Standby,
} from '../model/types'

export async function fetchOvertime(status: string | null): Promise<Overtime[]> {
  return unwrap(
    await api.GET('/api/v1/overtime/requests', {
      params: { query: status === null ? {} : { status: status as OvertimeStatus } },
    }),
  )
}

export async function askForOvertime(body: OvertimeBody): Promise<Overtime> {
  return unwrap(await api.POST('/api/v1/overtime/requests', { body }))
}

export type Decide = 'approve' | 'reject' | 'cancel'

export async function decideOvertime(requestId: number, what: Decide): Promise<Overtime> {
  const path = `/api/v1/overtime/requests/{request_id}/${what}` as const
  return unwrap(await api.POST(path, { params: { path: { request_id: requestId } } }))
}

export async function fetchPay(): Promise<PayStatus[]> {
  return unwrap(await api.GET('/api/v1/overtime/pay'))
}

export async function savePay(employeeId: number, body: PayBody): Promise<PayStatus> {
  return unwrap(
    await api.PUT('/api/v1/overtime/pay/{employee_id}', {
      params: { path: { employee_id: employeeId } },
      body,
    }),
  )
}

export async function recordWorked(requestId: number, minutes: number): Promise<Overtime> {
  return unwrap(
    await api.POST('/api/v1/overtime/requests/{request_id}/worked', {
      params: { path: { request_id: requestId } },
      body: { minutes },
    }),
  )
}

/** `month` is any day of the month, as YYYY-MM-DD. */
export async function fetchSummary(month: string): Promise<OvertimeSummary> {
  return unwrap(await api.GET('/api/v1/overtime/summary', { params: { query: { month } } }))
}

export async function saveStandbyAllowance(standbyAllowance: number): Promise<void> {
  unwrap(await api.PUT('/api/v1/overtime/rates', { body: { standbyAllowance } }))
}

export async function saveBudget(month: string, amount: number | null): Promise<void> {
  unwrap(
    await api.PUT('/api/v1/overtime/budget/{month}', {
      params: { path: { month } },
      body: { amount },
    }),
  )
}

export async function fetchStandby(): Promise<Standby[]> {
  return unwrap(await api.GET('/api/v1/overtime/standby'))
}

export async function bookStandby(employeeId: number, day: string): Promise<Standby> {
  return unwrap(await api.POST('/api/v1/overtime/standby', { body: { employeeId, day } }))
}

export async function cancelStandby(standbyId: number): Promise<Standby> {
  return unwrap(
    await api.POST('/api/v1/overtime/standby/{standby_id}/cancel', {
      params: { path: { standby_id: standbyId } },
    }),
  )
}

export async function recordCallOut(standbyId: number, minutes: number): Promise<Standby> {
  return unwrap(
    await api.POST('/api/v1/overtime/standby/{standby_id}/call-out', {
      params: { path: { standby_id: standbyId } },
      body: { minutes },
    }),
  )
}
