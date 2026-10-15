import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { contractKeys, createCustomer } from '@/entities/contract'
import { refreshQueries } from '@/shared/lib/refresh'

export function useAddCustomer() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => createCustomer(name),
    onSuccess: () => refreshQueries(queryClient, contractKeys.all),
  })
}
