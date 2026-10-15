import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { callDataKeys } from '@/entities/call-data'
import {
  contractKeys,
  createContract,
  updateContract,
  type ContractChange,
  type NewContract,
} from '@/entities/contract'
import { refreshQueries } from '@/shared/lib/refresh'

/** A contract writes its target onto its queues, so the queue lists refresh with the contracts. */
export function useSaveContract() {
  const queryClient = useQueryClient()
  const refresh = () => refreshQueries(queryClient, contractKeys.all, callDataKeys.all)
  return {
    create: useMutation({
      mutationFn: (body: NewContract) => createContract(body),
      onSuccess: refresh,
    }),
    update: useMutation({
      mutationFn: (v: { id: number; body: ContractChange }) => updateContract(v.id, v.body),
      onSuccess: refresh,
    }),
  }
}
