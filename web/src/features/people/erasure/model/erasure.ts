import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import { schedulingKeys } from '@/entities/scheduling'
import { api, unwrap, type components } from '@/shared/api'
import { refreshQueries } from '@/shared/lib/refresh'

export type ErasurePreview = components['schemas']['ErasurePreviewOut']
export type Retention = components['schemas']['RetentionOut']

const retentionKey = ['people', 'retention'] as const

/** What would be removed and kept, or a problem saying why this person cannot be anonymised. */
export function useErasurePreview() {
  return useMutation({
    mutationFn: async (employeeId: number): Promise<ErasurePreview> =>
      unwrap(
        await api.POST('/api/v1/people/employees/{employee_id}/erasure-request', {
          params: { path: { employee_id: employeeId } },
        }),
      ),
  })
}

/** Anonymise for good. `employeeNumber` is what the admin typed, which the server checks again. */
export function useAnonymise() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (v: { employeeId: number; employeeNumber: string }) =>
      unwrap(
        await api.POST('/api/v1/people/employees/{employee_id}/anonymise', {
          params: { path: { employee_id: v.employeeId } },
          body: { employeeNumber: v.employeeNumber },
        }),
      ),
    onSuccess: () => refreshQueries(queryClient, schedulingKeys.all, retentionKey),
  })
}

/** Leavers past the retention period. Admin only; the server refuses everyone else. */
export function useRetention() {
  return useQuery({
    queryKey: retentionKey,
    queryFn: async (): Promise<Retention> => unwrap(await api.GET('/api/v1/people/retention')),
  })
}
