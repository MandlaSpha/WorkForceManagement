import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { schedulingKeys, setAgentLogins } from '@/entities/scheduling'
import { refreshQueries } from '@/shared/lib/refresh'

export function useMapLogins() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (v: { employeeId: number; logins: string[] }) =>
      setAgentLogins(v.employeeId, v.logins),
    onSuccess: () => refreshQueries(queryClient, schedulingKeys.all),
  })
}
