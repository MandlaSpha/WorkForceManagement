import { api, unwrap } from '@/shared/api'

import type { Overtime, OvertimeBody, OvertimeStatus, PayBody, PayStatus } from '../model/types'

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
