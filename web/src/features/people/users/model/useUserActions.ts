import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { schedulingKeys } from '@/entities/scheduling'
import {
  createUser,
  linkEmployeeLogin,
  resetUserPassword,
  setUserActive,
  setUserRole,
  unlockUser,
  userKeys,
} from '@/entities/user-admin'
import type { NewUser } from '@/entities/user-admin'
import { refreshQueries } from '@/shared/lib/refresh'

/** One mutation per thing an admin can do to a user; each refreshes the user list (and the
 * employee lists, because linking changes who an employee is). */
export function useUserActions() {
  const queryClient = useQueryClient()
  const refresh = () => refreshQueries(queryClient, userKeys.all, schedulingKeys.all)
  return {
    create: useMutation({ mutationFn: (body: NewUser) => createUser(body), onSuccess: refresh }),
    role: useMutation({
      mutationFn: (v: { id: number; role: string }) => setUserRole(v.id, v.role),
      onSuccess: refresh,
    }),
    active: useMutation({
      mutationFn: (v: { id: number; active: boolean }) => setUserActive(v.id, v.active),
      onSuccess: refresh,
    }),
    unlock: useMutation({ mutationFn: (id: number) => unlockUser(id), onSuccess: refresh }),
    reset: useMutation({
      mutationFn: (v: { id: number; password: string }) => resetUserPassword(v.id, v.password),
      onSuccess: refresh,
    }),
    link: useMutation({
      mutationFn: (v: { employeeId: number; userId: number | null }) =>
        linkEmployeeLogin(v.employeeId, v.userId),
      onSuccess: refresh,
    }),
  }
}
