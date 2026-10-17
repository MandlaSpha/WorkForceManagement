import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { saveCredentials, skillKeys, type CredentialInput } from '@/entities/workforce/skills'
import { refreshQueries } from '@/shared/lib/refresh'

/** Replace one person's credentials; every cached skills answer (lists, gaps) is refreshed. */
export function useSaveCredentials() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (vars: { employeeId: number; credentials: CredentialInput[] }) =>
      saveCredentials(vars.employeeId, vars.credentials),
    onSuccess: () => refreshQueries(queryClient, skillKeys.all),
  })
}
