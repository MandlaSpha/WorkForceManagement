import { api, unwrap } from '@/shared/api'

import type {
  AssignRequest,
  AssignResult,
  Employee,
  EmployeeRequest,
  Plan,
  Roster,
  RosterWeek,
  Shift,
  ShiftRequest,
} from '../model/types'

export async function fetchShifts(): Promise<Shift[]> {
  return unwrap(await api.GET('/api/v1/scheduling/shifts'))
}

export async function createShift(body: ShiftRequest): Promise<Shift> {
  return unwrap(await api.POST('/api/v1/scheduling/shifts', { body }))
}

export async function deleteShift(shiftId: number): Promise<void> {
  unwrap(
    await api.DELETE('/api/v1/scheduling/shifts/{shift_id}', {
      params: { path: { shift_id: shiftId } },
    }),
  )
}

export async function fetchEmployees(queueId: number | null): Promise<Employee[]> {
  return unwrap(
    await api.GET('/api/v1/scheduling/employees', {
      params: { query: queueId === null ? {} : { queue_id: queueId } },
    }),
  )
}

export async function createEmployee(body: EmployeeRequest): Promise<Employee> {
  return unwrap(await api.POST('/api/v1/scheduling/employees', { body }))
}

export async function updateEmployee(id: number, body: EmployeeRequest): Promise<Employee> {
  return unwrap(
    await api.PUT('/api/v1/scheduling/employees/{employee_id}', {
      params: { path: { employee_id: id } },
      body,
    }),
  )
}

export async function fetchRoster(queueId: number, weekStart: string): Promise<Roster> {
  return unwrap(
    await api.GET('/api/v1/scheduling/roster', {
      params: { query: { queue_id: queueId, week_start: weekStart } },
    }),
  )
}

export async function assignShift(body: AssignRequest): Promise<AssignResult> {
  return unwrap(await api.PUT('/api/v1/scheduling/roster/assignments', { body }))
}

export async function publishRoster(queueId: number, weekStart: string): Promise<RosterWeek> {
  return unwrap(
    await api.POST('/api/v1/scheduling/roster/publish', { body: { queueId, weekStart } }),
  )
}

export async function reopenRoster(queueId: number, weekStart: string): Promise<RosterWeek> {
  return unwrap(
    await api.POST('/api/v1/scheduling/roster/reopen', { body: { queueId, weekStart } }),
  )
}

export async function fetchPlan(queueId: number, weekStart: string): Promise<Plan> {
  return unwrap(
    await api.GET('/api/v1/scheduling/plan', {
      params: { query: { queue_id: queueId, week_start: weekStart } },
    }),
  )
}

/** Where the browser downloads the roster as CSV. A plain link, so the browser handles the file
 * and sends the session cookie itself. */
export function rosterExportUrl(queueId: number, weekStart: string): string {
  return `/api/v1/scheduling/roster/export.csv?queue_id=${queueId}&week_start=${weekStart}`
}
