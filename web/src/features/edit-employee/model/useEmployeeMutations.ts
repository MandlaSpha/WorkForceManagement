import { useMutation, useQueryClient } from '@tanstack/vue-query'

import {
  createEmployee,
  schedulingKeys,
  updateEmployee,
  type EmployeeRequest,
} from '@/entities/scheduling'
import { refreshQueries } from '@/shared/lib/refresh'

/** Add a person, or change one. Every list that shows people and rosters is refreshed. */
export function useEmployeeMutations() {
  const queryClient = useQueryClient()
  const refresh = () => refreshQueries(queryClient, schedulingKeys.all)
  return {
    create: useMutation({
      mutationFn: (body: EmployeeRequest) => createEmployee(body),
      onSuccess: refresh,
    }),
    update: useMutation({
      mutationFn: (v: { id: number; body: EmployeeRequest }) => updateEmployee(v.id, v.body),
      onSuccess: refresh,
    }),
  }
}
