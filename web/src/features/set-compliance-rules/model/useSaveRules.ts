import { useMutation, useQueryClient } from '@tanstack/vue-query'

import {
  saveComplianceRules,
  schedulingKeys,
  type ComplianceRulesRequest,
} from '@/entities/scheduling'
import { refreshQueries } from '@/shared/lib/refresh'

/** Rosters are checked against the rules, so a change refreshes everything scheduling shows. */
export function useSaveRules() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ComplianceRulesRequest) => saveComplianceRules(body),
    onSuccess: () => refreshQueries(queryClient, schedulingKeys.all),
  })
}
