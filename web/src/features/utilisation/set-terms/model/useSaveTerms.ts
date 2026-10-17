import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { saveTerms, utilisationKeys, type TermsInput } from '@/entities/workforce/utilisation'
import { refreshQueries } from '@/shared/lib/refresh'

/** Save a contract's target and revenue; the utilisation and cost answers are then refreshed. */
export function useSaveTerms() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (vars: { contractId: number; terms: TermsInput }) =>
      saveTerms(vars.contractId, vars.terms),
    onSuccess: () => refreshQueries(queryClient, utilisationKeys.all),
  })
}
