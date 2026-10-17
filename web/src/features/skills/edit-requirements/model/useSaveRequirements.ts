import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { saveRequirements, skillKeys, type RequirementInput } from '@/entities/workforce/skills'
import { refreshQueries } from '@/shared/lib/refresh'

/** Replace what one queue requires; the requirement lists and the gaps are refreshed. */
export function useSaveRequirements() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (vars: { queueId: number; requirements: RequirementInput[] }) =>
      saveRequirements(vars.queueId, vars.requirements),
    onSuccess: () => refreshQueries(queryClient, skillKeys.all),
  })
}
