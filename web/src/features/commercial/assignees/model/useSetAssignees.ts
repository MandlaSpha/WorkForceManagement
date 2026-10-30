import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { contractKeys, setAssignees } from '@/entities/contract'
import { refreshQueries } from '@/shared/lib/refresh'

/** Who looks after a customer decides which contracts a customer operations manager sees. */
export function useSetAssignees() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (v: { customerId: number; userIds: number[] }) =>
      setAssignees(v.customerId, v.userIds),
    onSuccess: () => refreshQueries(queryClient, contractKeys.all),
  })
}
