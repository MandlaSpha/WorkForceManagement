import { api, unwrap } from '@/shared/api'

import type { AdminUser, NewUser } from '../model/types'

export async function fetchUsers(): Promise<AdminUser[]> {
  return unwrap(await api.GET('/api/v1/users'))
}

export async function createUser(body: NewUser): Promise<AdminUser> {
  return unwrap(await api.POST('/api/v1/users', { body }))
}

export async function setUserRole(userId: number, role: string): Promise<AdminUser> {
  return unwrap(
    await api.PUT('/api/v1/users/{user_id}/role', {
      params: { path: { user_id: userId } },
      body: { role },
    }),
  )
}

export async function setUserActive(userId: number, active: boolean): Promise<AdminUser> {
  return unwrap(
    await api.PUT('/api/v1/users/{user_id}/active', {
      params: { path: { user_id: userId } },
      body: { active },
    }),
  )
}

export async function unlockUser(userId: number): Promise<AdminUser> {
  return unwrap(
    await api.POST('/api/v1/users/{user_id}/unlock', { params: { path: { user_id: userId } } }),
  )
}

export async function resetUserPassword(userId: number, password: string): Promise<AdminUser> {
  return unwrap(
    await api.POST('/api/v1/users/{user_id}/password', {
      params: { path: { user_id: userId } },
      body: { password },
    }),
  )
}

/** Tie an employee record to a login (or untie it with null). */
export async function linkEmployeeLogin(employeeId: number, userId: number | null): Promise<void> {
  unwrap(
    await api.PUT('/api/v1/scheduling/employees/{employee_id}/login', {
      params: { path: { employee_id: employeeId } },
      body: { userId },
    }),
  )
}
